"""Soak the Scorbot with small out-and-back moves.

The physical arm is only commanded with ``--real``. Otherwise the same cycle
runs on the digital twin. Motion is a few degrees around the pose captured at
start: one axis at a time, out and back. This script does not home. Homing
drives into the switches, and Operator already homes when it starts.

Base moves use polar pan. With the ER-V oversteer mode set to abort, Operator
sends HERE, shift, clrbuf, then MOVE, so each pan is relative to the live
pose. Shoulder, elbow, and pitch use the joint-relative hardware command,
which is the same HERE / shift / clrbuf / MOVE sequence.

A controller fault is cleared the way Commander already clears one.
``Publisher.erv_enable_control`` sends ACL ``CON``, which is what the web
console and the digital twin's real backend send. On the twin, the same step
calls ``SimulatedRobot.clear_fault``. An impact or a command the controller
does not recognize is cleared once, then the soak stops.

Run from ``commander``::

    uv run python -m src.burn_in --moves 4
    uv run python -m src.burn_in --real --host bluey.local --hours 3

Watch a short ``--moves`` run before leaving a multi-hour one going. Stay
near the power switch. A MOVE the controller has already accepted will finish;
each one is only a couple of degrees.
"""

from __future__ import annotations

import argparse
import signal
import threading
import time
from dataclasses import dataclass, replace

from src.simulation.erv_calibration import BASE_CALIBRATION
from src.simulation.publisher import SimulatedPublisher
from src.simulation.robot import SimulatedRobot

AXES = ("base", "shoulder", "elbow", "pitch")

# Hard limits. The CLI cannot raise these.
MIN_INTERVAL_S = 4.0
MAX_INTERVAL_S = 30.0
MAX_HOURS = 8.0
MAX_SPEED_PERCENT = 25
MAX_AZIMUTH_DEG = 5
MAX_SHOULDER_COUNTS = 80
MAX_ELBOW_COUNTS = 80
MAX_PITCH_COUNTS = 24
MAX_CONSECUTIVE_FAULTS = 3
MAX_TOTAL_FAULTS = 12
NO_PROGRESS_LIMIT = 3
SETTLE_WINDOW_S = 0.4
COUNT_DEADBAND = 5
STALE_TELEMETRY_S = 2.5

_FAULT_MARKERS = (
    "IMPACT",
    "CONTROL DISABLED",
    "FAULT",
    "ERROR",
    "UNRECOGNIZED REQUEST",
    "NOT FOUND",
)


@dataclass(frozen=True)
class PoseCounts:
    """Controller coordinates from a TELP frame."""

    base: int
    shoulder: int
    elbow: int
    pitch: int

    def axis(self, name: str) -> int:
        return getattr(self, name)


@dataclass(frozen=True)
class Move:
    """One discrete command. Base and the arm joints are never combined."""

    axis: str
    base_degrees: int = 0
    shoulder: int = 0
    elbow: int = 0
    pitch: int = 0

    @property
    def idle(self) -> bool:
        return (
            self.base_degrees == 0
            and self.shoulder == 0
            and self.elbow == 0
            and self.pitch == 0
        )


@dataclass(frozen=True)
class BurnInConfig:
    duration_s: float = 3 * 60 * 60
    interval_s: float = 5.0
    speed_percent: int = 15
    azimuth_step_deg: int = 2
    shoulder_step_counts: int = 40
    elbow_step_counts: int = 40
    pitch_step_counts: int = 12
    move_limit: int = 0

    def __post_init__(self) -> None:
        if not 0 < self.duration_s <= MAX_HOURS * 60 * 60:
            raise ValueError(f"duration must be within 0 and {MAX_HOURS:g} hours")
        if not MIN_INTERVAL_S <= self.interval_s <= MAX_INTERVAL_S:
            raise ValueError(
                f"interval must be within {MIN_INTERVAL_S:g} and {MAX_INTERVAL_S:g} seconds"
            )
        if not 1 <= self.speed_percent <= MAX_SPEED_PERCENT:
            raise ValueError(f"speed must be within 1 and {MAX_SPEED_PERCENT} percent")
        if not 0 <= self.azimuth_step_deg <= MAX_AZIMUTH_DEG:
            raise ValueError(f"azimuth step must be within 0 and {MAX_AZIMUTH_DEG} degrees")
        if not 0 <= self.shoulder_step_counts <= MAX_SHOULDER_COUNTS:
            raise ValueError(f"shoulder step must be within 0 and {MAX_SHOULDER_COUNTS} counts")
        if not 0 <= self.elbow_step_counts <= MAX_ELBOW_COUNTS:
            raise ValueError(f"elbow step must be within 0 and {MAX_ELBOW_COUNTS} counts")
        if not 0 <= self.pitch_step_counts <= MAX_PITCH_COUNTS:
            raise ValueError(f"pitch step must be within 0 and {MAX_PITCH_COUNTS} counts")
        if self.move_limit < 0:
            raise ValueError("move limit cannot be negative")
        if all(step_counts(self, axis) == 0 for axis in AXES):
            raise ValueError("at least one axis has to move")


@dataclass(frozen=True)
class BurnInResult:
    code: int
    commands: int
    faults_cleared: int
    reason: str


class WallClock:
    def time(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


def controller_shift_counts(degrees: int) -> int:
    """Match Operator's C cast of ``degrees * counts_per_degree``, toward zero."""

    return int(degrees * BASE_CALIBRATION.counts_per_degree)


def step_counts(config: BurnInConfig, axis: str) -> int:
    if axis == "base":
        return abs(controller_shift_counts(config.azimuth_step_deg))
    if axis == "shoulder":
        return config.shoulder_step_counts
    if axis == "elbow":
        return config.elbow_step_counts
    if axis == "pitch":
        return config.pitch_step_counts
    raise KeyError(axis)


def abort_radius(config: BurnInConfig, axis: str) -> int:
    """How far from the start pose is still a soak, rather than a runaway."""

    floor = 80 if axis == "base" else 25
    return max(floor, step_counts(config, axis) * 3)


def base_command_degrees(delta_counts: int, max_deg: int) -> int:
    """Largest degree step toward ``delta_counts`` that does not pass the target."""

    if max_deg <= 0 or delta_counts == 0:
        return 0
    sign = 1 if delta_counts > 0 else -1
    remaining = abs(delta_counts)
    best = 0
    for degrees in range(1, max_deg + 1):
        shift = abs(controller_shift_counts(degrees))
        if shift <= remaining + 2:
            best = degrees
        else:
            break
    return sign * best


def _clamp_counts(delta: int, step: int) -> int:
    if step <= 0 or abs(delta) < 2:
        return 0
    if delta > step:
        return step
    if delta < -step:
        return -step
    return delta


def plan_step(origin: PoseCounts, current: PoseCounts, axis: str, sign: int, config: BurnInConfig) -> Move:
    """Plan one approach toward ``origin + sign * step`` on a single axis."""

    if axis not in AXES or sign not in (-1, 0, 1):
        raise ValueError(f"cannot plan {axis} sign {sign}")
    target = origin.axis(axis) + sign * step_counts(config, axis)
    delta = target - current.axis(axis)
    if axis == "base":
        return Move(axis, base_degrees=base_command_degrees(delta, config.azimuth_step_deg))
    commanded = _clamp_counts(delta, step_counts(config, axis))
    if axis == "shoulder":
        return Move(axis, shoulder=commanded)
    if axis == "elbow":
        return Move(axis, elbow=commanded)
    return Move(axis, pitch=commanded)


def cycle(config: BurnInConfig) -> tuple[tuple[str, int], ...]:
    """Out, back to the start, the other way, and back, for each live axis."""

    steps: list[tuple[str, int]] = []
    for axis in AXES:
        if step_counts(config, axis) == 0:
            continue
        steps.extend(((axis, 1), (axis, 0), (axis, -1), (axis, 0)))
    return tuple(steps)


def envelope_breach(origin: PoseCounts, current: PoseCounts, config: BurnInConfig) -> str | None:
    for axis in AXES:
        delta = abs(current.axis(axis) - origin.axis(axis))
        limit = abort_radius(config, axis)
        if delta > limit:
            return f"{axis} is {delta} counts from the start (limit {limit})"
    return None


def fault_text(line: str) -> str | None:
    """Return an Operator fault line, ignoring telemetry and receipts."""

    text = line.strip()
    if not text or text.startswith("TEL") or text == "ACK":
        return None
    upper = text.upper()
    if any(marker in upper for marker in _FAULT_MARKERS):
        return text[:500]
    return None


def fault_kind(message: str) -> str:
    upper = message.upper()
    if "IMPACT" in upper:
        return "impact"
    if "UNRECOGNIZED" in upper or "NOT FOUND" in upper:
        return "protocol"
    return "recoverable"


def pose_from_telemetry(counts: tuple[int, ...] | None) -> PoseCounts | None:
    """Read a TELP frame. Current Operator frames lead with the base."""

    if counts is None or len(counts) < 5:
        return None
    base, shoulder, elbow, pitch = counts[:4]
    return PoseCounts(int(base), int(shoulder), int(elbow), int(pitch))


def _settled(left: PoseCounts, right: PoseCounts) -> bool:
    return all(abs(left.axis(axis) - right.axis(axis)) <= COUNT_DEADBAND for axis in AXES)


def _format_pose(pose: PoseCounts) -> str:
    return (
        f"base={pose.base} shoulder={pose.shoulder} "
        f"elbow={pose.elbow} pitch={pose.pitch}"
    )


def _format_move(move: Move) -> str:
    if move.base_degrees:
        return f"base {move.base_degrees:+d} deg"
    if move.shoulder:
        return f"shoulder {move.shoulder:+d} counts"
    if move.elbow:
        return f"elbow {move.elbow:+d} counts"
    if move.pitch:
        return f"pitch {move.pitch:+d} counts"
    return f"{move.axis} hold"


def log(message: str) -> None:
    print(f"{time.strftime('%H:%M:%S')}  {message}", flush=True)


class RealArm:
    """Live Operator link. Fault lines latch until the soak handles them."""

    def __init__(self, publisher, clock: WallClock | None = None, stop: threading.Event | None = None) -> None:
        self.publisher = publisher
        self._clock = clock or WallClock()
        self._stop = stop or threading.Event()
        self._lock = threading.Lock()
        self._fault: str | None = None
        self._speed = 15
        self._closed = False
        self.publisher.operator_connection.add_message_listener(self._on_message)

    def _on_message(self, line: str) -> None:
        fault = fault_text(line)
        if fault is None:
            return
        with self._lock:
            self._fault = fault

    def peek_fault(self) -> str | None:
        with self._lock:
            return self._fault

    def pop_fault(self) -> str | None:
        with self._lock:
            fault = self._fault
            self._fault = None
            return fault

    def latest(self) -> tuple[PoseCounts | None, float | None]:
        pose = pose_from_telemetry(self.publisher.get_erv_joint_counts())
        stamp = self.publisher.get_erv_telemetry_received_monotonic()
        if pose is None or stamp is None:
            return None, None
        return pose, self._clock.time() - stamp

    def set_speed_percent(self, percent: int) -> None:
        self._speed = percent
        self.publisher.erv_set_speed_percent(percent)
        if not self._accepted():
            raise OSError("speed command was not accepted")

    def enable_control(self) -> None:
        """ACL CON, then the same speed cap again."""

        self.publisher.erv_enable_control()
        self.publisher.erv_set_speed_percent(self._speed)
        if not self._accepted():
            raise OSError("enable-control command was not accepted")

    def command(self, move: Move) -> bool:
        if move.idle or (move.base_degrees and (move.shoulder or move.elbow or move.pitch)):
            raise RuntimeError("refusing a move that is empty or mixes base and joints")
        if move.base_degrees:
            self.publisher.polar_pan_discrete(move.base_degrees, 0, 0, 1000)
        else:
            self.publisher.erv_joint_move_relative(move.shoulder, move.elbow, move.pitch)
        return self._accepted()

    def prepare(self) -> PoseCounts:
        self._wait_connected()
        self.publisher.handshake()
        pose = self._wait_settled(60)
        fault = self.pop_fault()
        if fault is None:
            return pose
        self.enable_control()
        if fault_kind(fault) != "recoverable":
            raise RuntimeError(f"refusing to start after {fault}")
        pose = self._wait_settled(15)
        lingering = self.peek_fault()
        if lingering:
            raise RuntimeError(f"fault did not clear: {lingering}")
        return pose

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        stop_motion = getattr(self.publisher, "polar_pan_continuous_stop", None)
        try:
            if stop_motion is not None and self.publisher.is_connected():
                stop_motion()
        except OSError:
            pass
        closer = getattr(self.publisher, "close", None)
        if closer is not None:
            try:
                closer()
            except OSError:
                pass

    def _accepted(self) -> bool:
        receipt = self.publisher.get_command_receipt()
        if not receipt:
            return False
        return not receipt.get("last_failed", False)

    def _wait_connected(self) -> None:
        deadline = self._clock.time() + 15
        while self._clock.time() < deadline:
            if self._stop.is_set():
                raise RuntimeError("stopped before Operator connected")
            if self.publisher.is_connected():
                return
            self._clock.sleep(0.1)
        raise RuntimeError("Operator did not connect")

    def _pose(self) -> PoseCounts | None:
        return pose_from_telemetry(self.publisher.get_erv_joint_counts())

    def _wait_settled(self, timeout_s: float) -> PoseCounts:
        deadline = self._clock.time() + timeout_s
        previous: PoseCounts | None = None
        stable_since: float | None = None
        announced = False
        while self._clock.time() < deadline:
            if self._stop.is_set():
                raise RuntimeError("stopped before the arm settled")
            if not announced:
                log("waiting for joint telemetry to settle")
                announced = True
            current = self._pose()
            now = self._clock.time()
            if current is None:
                previous = None
                stable_since = None
            elif previous is None or not _settled(previous, current):
                previous = current
                stable_since = now
            elif stable_since is not None and now - stable_since >= SETTLE_WINDOW_S:
                return current
            self._clock.sleep(0.1)
        raise RuntimeError(
            "no settled joint telemetry. If Operator just started it is still homing; "
            "wait until the arm is still, then run this again"
        )


class TwinArm:
    """Same cycle on the digital twin, including its fault latch."""

    def __init__(self) -> None:
        self.robot = SimulatedRobot()
        self.publisher = SimulatedPublisher(self.robot)
        # Vertical-straight controller references. The soak only nudges these.
        self.counts = PoseCounts(base=0, shoulder=1088, elbow=2113, pitch=1151)
        self._latched: str | None = None
        self._fail_next: str | None = None
        self.enable_calls = 0
        self.speed_percent: int | None = None
        self._closed = False

    def fail_next(self, message: str) -> None:
        self._fail_next = message

    def peek_fault(self) -> str | None:
        if self._latched:
            return self._latched
        fault = self.robot.get_state().fault
        if fault is None:
            return None
        return f"{fault.code}: {fault.message}"

    def pop_fault(self) -> str | None:
        message = self.peek_fault()
        self._latched = None
        return message

    def latest(self) -> tuple[PoseCounts | None, float | None]:
        return self.counts, 0.0

    def set_speed_percent(self, percent: int) -> None:
        self.speed_percent = percent
        self.publisher.set_speed(max(1, min(255, round(percent / 100 * 255))))

    def enable_control(self) -> None:
        self.enable_calls += 1
        self.publisher.clear_fault()
        self._latched = None

    def command(self, move: Move) -> bool:
        if self._fail_next:
            message = self._fail_next
            self._fail_next = None
            self.robot.inject_fault("burn_in", message)
            self._latched = message
            return True
        try:
            if move.base_degrees:
                self.publisher.polar_pan_discrete(move.base_degrees, 0, 0, 500)
                self.robot.advance(5.0)
            elif move.pitch:
                # The twin's plant has altitude, not a wrist-pitch count.
                # The planner still reads the exact count model below.
                self.publisher.polar_pan_discrete(0, 1 if move.pitch > 0 else -1, 0, 500)
                self.robot.advance(5.0)
        except RuntimeError as exc:
            self._latched = str(exc)
            return True
        fault = self.robot.get_state().fault
        if fault is not None:
            self._latched = f"{fault.code}: {fault.message}"
            return True
        self.counts = replace(
            self.counts,
            base=self.counts.base + controller_shift_counts(move.base_degrees),
            shoulder=self.counts.shoulder + move.shoulder,
            elbow=self.counts.elbow + move.elbow,
            pitch=self.counts.pitch + move.pitch,
        )
        return True

    def prepare(self) -> PoseCounts:
        if not self.publisher.handshake():
            raise RuntimeError("digital twin is closed")
        return self.counts

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.publisher.polar_pan_continuous_stop()
        self.publisher.close()


def _dwell(seconds: float, arm, clock: WallClock, stop: threading.Event) -> str:
    end = clock.time() + seconds
    while clock.time() < end - 1e-9:
        if stop.is_set():
            return "stop"
        if arm.peek_fault():
            return "fault"
        clock.sleep(min(0.2, end - clock.time()))
    if stop.is_set():
        return "stop"
    if arm.peek_fault():
        return "fault"
    return "ok"


def _followed(before: PoseCounts, after: PoseCounts, move: Move) -> bool:
    if move.base_degrees:
        expected = abs(controller_shift_counts(move.base_degrees))
        return abs(after.base - before.base) >= expected * 0.4
    for axis, commanded in (
        ("shoulder", move.shoulder),
        ("elbow", move.elbow),
        ("pitch", move.pitch),
    ):
        if commanded and abs(after.axis(axis) - before.axis(axis)) >= max(2, abs(commanded) * 0.4):
            return True
    return False


def _runaway(before: PoseCounts, after: PoseCounts, move: Move) -> str | None:
    limits = {
        "base": abs(controller_shift_counts(move.base_degrees)) * 2 + 30,
        "shoulder": abs(move.shoulder) * 2 + 15,
        "elbow": abs(move.elbow) * 2 + 15,
        "pitch": abs(move.pitch) * 2 + 15,
    }
    # An axis we did not ask to move still has a small noise allowance.
    if move.base_degrees == 0:
        limits["base"] = 80
    if move.shoulder == 0:
        limits["shoulder"] = 40
    if move.elbow == 0:
        limits["elbow"] = 40
    if move.pitch == 0:
        limits["pitch"] = 40
    for axis, limit in limits.items():
        delta = abs(after.axis(axis) - before.axis(axis))
        if delta > limit:
            return f"{axis} changed {delta} counts on one move (limit {limit})"
    return None


def run_burn_in(
    arm,
    config: BurnInConfig,
    *,
    stop: threading.Event | None = None,
    clock: WallClock | None = None,
) -> BurnInResult:
    clock = clock or WallClock()
    stop = stop or threading.Event()
    try:
        origin = arm.prepare()
        arm.set_speed_percent(config.speed_percent)
    except (OSError, RuntimeError) as exc:
        if stop.is_set() or "stopped" in str(exc).lower():
            log("stopped")
            return BurnInResult(130, 0, 0, "stopped")
        log(str(exc))
        return BurnInResult(1, 0, 0, str(exc))

    steps = cycle(config)
    if not steps:
        return BurnInResult(1, 0, 0, "at least one axis has to move")
    log(
        f"start {_format_pose(origin)}; speed {config.speed_percent}%; "
        f"every {config.interval_s:g}s; {len(steps)} steps per cycle"
    )
    log("envelope " + ", ".join(f"{axis} ±{abort_radius(config, axis)} counts" for axis in AXES))

    commands = 0
    faults_cleared = 0
    consecutive = 0
    no_progress = 0
    waypoint = 0
    started = clock.time()

    def finish(code: int, reason: str) -> BurnInResult:
        log(reason)
        return BurnInResult(code, commands, faults_cleared, reason)

    def clear_fault(message: str) -> BurnInResult | None:
        nonlocal faults_cleared, consecutive
        consecutive += 1
        faults_cleared += 1
        log(f"fault {faults_cleared}: {message}")
        try:
            arm.enable_control()
        except OSError as exc:
            return finish(8, f"could not clear the fault: {exc}")
        kind = fault_kind(message)
        if kind == "impact":
            return finish(5, "cleared an impact fault and stopped")
        if kind == "protocol":
            return finish(5, "cleared a protocol fault and stopped")
        if consecutive >= MAX_CONSECUTIVE_FAULTS or faults_cleared >= MAX_TOTAL_FAULTS:
            return finish(2, f"cleared {faults_cleared} faults and stopped")
        try:
            paused = _dwell(config.interval_s, arm, clock, stop)
        except KeyboardInterrupt:
            stop.set()
            paused = "stop"
        if paused == "stop":
            return finish(130, "stopped")
        if paused == "fault":
            return None
        return None

    while True:
        if stop.is_set():
            return finish(130, "stopped")
        # A fault on the last move still gets CON before the run is over.
        pending = arm.pop_fault()
        if pending:
            outcome = clear_fault(pending)
            if outcome is not None:
                return outcome
            continue
        elapsed = clock.time() - started
        if config.move_limit and commands >= config.move_limit:
            return finish(0, f"completed {commands} moves")
        if elapsed >= config.duration_s:
            return finish(0, f"completed {config.duration_s / 3600:g}h")

        current, age = arm.latest()
        if current is None or age is None or age > STALE_TELEMETRY_S:
            outcome = clear_fault("telemetry is stale")
            if outcome is not None:
                return outcome
            continue

        breach = envelope_breach(origin, current, config)
        if breach:
            return finish(4, f"left the safe envelope: {breach}")

        axis, sign = steps[waypoint % len(steps)]
        move = plan_step(origin, current, axis, sign, config)
        before = current
        if not move.idle:
            log(f"move {commands + 1}: {_format_move(move)} from {_format_pose(current)}")
            try:
                accepted = arm.command(move)
            except (OSError, RuntimeError) as exc:
                return finish(8, f"command failed: {exc}")
            if not accepted:
                return finish(8, "command was not accepted")
            commands += 1

        try:
            paused = _dwell(config.interval_s, arm, clock, stop)
        except KeyboardInterrupt:
            stop.set()
            paused = "stop"
        if paused == "stop":
            return finish(130, "stopped")
        if paused == "fault":
            continue

        if move.idle:
            waypoint += 1
            continue

        current, age = arm.latest()
        if current is None or age is None or age > STALE_TELEMETRY_S:
            outcome = clear_fault("telemetry is stale")
            if outcome is not None:
                return outcome
            continue
        breach = envelope_breach(origin, current, config)
        if breach:
            return finish(4, f"left the safe envelope: {breach}")
        ran = _runaway(before, current, move)
        if ran:
            return finish(7, f"stopped: {ran}")
        if not _followed(before, current, move):
            no_progress += 1
            log(f"move did not show up in telemetry ({no_progress}/{NO_PROGRESS_LIMIT})")
            if no_progress >= NO_PROGRESS_LIMIT:
                return finish(6, "arm is not following commands")
            continue

        consecutive = 0
        no_progress = 0
        waypoint += 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Move the ER-V a few degrees at a time for a long soak test."
    )
    parser.add_argument(
        "--real",
        action="store_true",
        help="Command the physical robot through Operator. Omit this to use the digital twin.",
    )
    parser.add_argument("--host", default="bluey.local")
    parser.add_argument("--port", type=int, default=61616)
    parser.add_argument("--hours", type=float, default=3.0)
    parser.add_argument(
        "--moves",
        type=int,
        default=0,
        help="Stop after this many commands. 0 runs until --hours.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=5.0,
        help="Seconds between moves, from 4 to 30. Raise it if a move is still running.",
    )
    parser.add_argument("--speed", type=int, default=15, help=f"1..{MAX_SPEED_PERCENT} percent")
    parser.add_argument("--azimuth-deg", type=int, default=2)
    parser.add_argument("--shoulder-counts", type=int, default=40)
    parser.add_argument("--elbow-counts", type=int, default=40)
    parser.add_argument("--pitch-counts", type=int, default=12)
    return parser


def config_from_args(args: argparse.Namespace) -> BurnInConfig:
    if not args.host or not 1 <= args.port <= 65535:
        raise ValueError("host and port must be a real Operator address")
    return BurnInConfig(
        duration_s=args.hours * 60 * 60,
        interval_s=args.interval,
        speed_percent=args.speed,
        azimuth_step_deg=args.azimuth_deg,
        shoulder_step_counts=args.shoulder_counts,
        elbow_step_counts=args.elbow_counts,
        pitch_step_counts=args.pitch_counts,
        move_limit=args.moves,
    )


def _countdown(stop: threading.Event) -> bool:
    log("starting in 5 seconds. Ctrl-C leaves the arm where it is.")
    for _ in range(5):
        if stop.is_set():
            return False
        time.sleep(1)
    return not stop.is_set()


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        config = config_from_args(args)
    except ValueError as exc:
        log(str(exc))
        return 1

    stop = threading.Event()

    def _request_stop(_signum, _frame) -> None:
        stop.set()
        log("stop requested. No further moves will be sent.")

    previous = {}
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            previous[sig] = signal.signal(sig, _request_stop)
        except ValueError:
            pass

    arm = None
    try:
        if args.real:
            log(
                f"REAL robot {args.host}:{args.port}. "
                "Close Commander and the digital twin viewer first so nothing else commands it."
            )
            log(
                f"±{config.azimuth_step_deg}° base, "
                f"±{config.shoulder_step_counts} shoulder counts, "
                f"±{config.elbow_step_counts} elbow counts, "
                f"±{config.pitch_step_counts} pitch counts, "
                f"at {config.speed_percent}% ."
            )
            log("This does not home. Keep the workspace clear and stay at the power switch.")
            log("Watch a --moves 4 run before leaving a multi-hour soak going.")
            if not _countdown(stop):
                return 130
            from src.connection.publisher import Publisher

            publisher = Publisher(args.host, args.port)
            arm = RealArm(publisher, stop=stop)
        else:
            log("Digital twin only. The physical robot will not move.")
            arm = TwinArm()
        result = run_burn_in(arm, config, stop=stop)
        return result.code
    except KeyboardInterrupt:
        log("stopped")
        return 130
    finally:
        if arm is not None:
            arm.close()
        for sig, handler in previous.items():
            signal.signal(sig, handler)


if __name__ == "__main__":
    raise SystemExit(main())
