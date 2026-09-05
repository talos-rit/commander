"""A deterministic kinematic robot model with no hardware dependencies.

The model deliberately uses Commander's existing polar and Cartesian command units.
It is not a kinematic model of a specific Scorbot: polar and Cartesian values are
independent logical axes.  A future physics backend can implement the same command
surface while deriving those values from its joint/link state.

The precise assumptions are normative for this mock and documented in
``src/simulation/README.md``. In particular, polar values are *not* assumed to be
degrees because the current ICD does not define their unit.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum

from src.robot_state import LogicalPose


AXES = ("azimuth", "altitude", "x", "y", "z")


@dataclass(frozen=True)
class RobotPose(LogicalPose):
    """Logical pose in ICD units (Cartesian values are tenths of millimetres).

    The current ICD does not define units for discrete azimuth/altitude commands.
    The simulator intentionally preserves their numeric values without guessing.
    """

    pass


@dataclass(frozen=True)
class AxisLimits:
    minimum: float
    maximum: float

    def __post_init__(self) -> None:
        if not self.minimum < self.maximum:
            raise ValueError("axis minimum must be less than its maximum")

    def contains(self, value: float) -> bool:
        return self.minimum <= value <= self.maximum


@dataclass(frozen=True)
class RobotLimits:
    azimuth: AxisLimits = field(default_factory=lambda: AxisLimits(-180.0, 180.0))
    altitude: AxisLimits = field(default_factory=lambda: AxisLimits(-90.0, 90.0))
    x: AxisLimits = field(default_factory=lambda: AxisLimits(-1000.0, 1000.0))
    y: AxisLimits = field(default_factory=lambda: AxisLimits(-1000.0, 1000.0))
    z: AxisLimits = field(default_factory=lambda: AxisLimits(-1000.0, 1000.0))

    def for_axis(self, axis: str) -> AxisLimits:
        return getattr(self, axis)

    def contains(self, pose: RobotPose) -> bool:
        return all(self.for_axis(axis).contains(getattr(pose, axis)) for axis in AXES)


class MovementState(str, Enum):
    IDLE = "idle"
    WAITING = "waiting"
    MOVING = "moving"
    HOMING = "homing"
    SETTLING = "settling"
    FAULTED = "faulted"


class CommandKind(str, Enum):
    HOME = "home"
    MOVE_TO = "move_to"
    CONTINUOUS = "continuous"


class CommandStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    SETTLING = "settling"
    COMPLETED = "completed"
    CANCELED = "canceled"
    REJECTED = "rejected"


@dataclass(frozen=True)
class FaultState:
    code: str
    message: str
    timestamp: float


@dataclass(frozen=True)
class RobotCommand:
    command_id: int
    kind: CommandKind
    status: CommandStatus
    issued_at: float
    starts_at: float
    target: RobotPose | None = None
    direction: RobotPose | None = None


@dataclass(frozen=True)
class RobotTimestamps:
    created_at: float
    updated_at: float
    command_issued_at: float | None = None
    movement_started_at: float | None = None
    movement_stopped_at: float | None = None
    command_completed_at: float | None = None


@dataclass(frozen=True)
class RobotState:
    pose: RobotPose
    movement_state: MovementState
    velocity: RobotPose
    movement_limits: RobotLimits
    homed: bool
    current_command: RobotCommand | None
    fault: FaultState | None
    timestamps: RobotTimestamps


@dataclass(frozen=True)
class SimulationConfig:
    """Configuration for the deterministic plant.

    Speeds are per second in the units used by :class:`RobotPose`.
    """

    initial_pose: RobotPose = field(default_factory=RobotPose)
    home_pose: RobotPose = field(default_factory=RobotPose)
    limits: RobotLimits = field(default_factory=RobotLimits)
    speed: RobotPose = field(
        default_factory=lambda: RobotPose(
            azimuth=30.0, altitude=30.0, x=100.0, y=100.0, z=100.0
        )
    )
    homing_speed: RobotPose = field(
        default_factory=lambda: RobotPose(
            azimuth=15.0, altitude=15.0, x=50.0, y=50.0, z=50.0
        )
    )
    command_latency: float = 0.0
    settling_time: float = 0.0

    def __post_init__(self) -> None:
        if (
            not math.isfinite(self.command_latency)
            or not math.isfinite(self.settling_time)
            or self.command_latency < 0
            or self.settling_time < 0
        ):
            raise ValueError("latency and settling time must be non-negative")
        if not self.limits.contains(self.initial_pose):
            raise ValueError("initial pose is outside movement limits")
        if not self.limits.contains(self.home_pose):
            raise ValueError("home pose is outside movement limits")
        for speeds in (self.speed, self.homing_speed):
            if any(
                not math.isfinite(getattr(speeds, axis))
                or getattr(speeds, axis) < 0
                for axis in AXES
            ):
                raise ValueError("axis speeds must be non-negative")


class ManualClock:
    """A clock advanced explicitly by tests or replay code."""

    def __init__(self, initial_time: float = 0.0) -> None:
        if not math.isfinite(initial_time):
            raise ValueError("initial time must be finite")
        self._time = float(initial_time)

    def now(self) -> float:
        return self._time

    def advance(self, seconds: float) -> float:
        if not math.isfinite(seconds) or seconds < 0:
            raise ValueError("clock advance must be finite and non-negative")
        self._time += seconds
        return self._time


@dataclass
class _ActiveCommand:
    command_id: int
    kind: CommandKind
    status: CommandStatus
    issued_at: float
    starts_at: float
    target: RobotPose | None = None
    direction: RobotPose | None = None
    start_pose: RobotPose | None = None
    velocity: RobotPose = field(default_factory=RobotPose)
    movement_ends_at: float | None = None
    settling_ends_at: float | None = None

    def snapshot(self) -> RobotCommand:
        return RobotCommand(
            command_id=self.command_id,
            kind=self.kind,
            status=self.status,
            issued_at=self.issued_at,
            starts_at=self.starts_at,
            target=self.target,
            direction=self.direction,
        )


def _pose_from_values(values: dict[str, float]) -> RobotPose:
    return RobotPose(**{axis: values[axis] for axis in AXES})


def _pose_add(left: RobotPose, right: RobotPose) -> RobotPose:
    return _pose_from_values(
        {axis: getattr(left, axis) + getattr(right, axis) for axis in AXES}
    )


def _pose_scale(pose: RobotPose, scale: float) -> RobotPose:
    return _pose_from_values({axis: getattr(pose, axis) * scale for axis in AXES})


class SimulatedRobot:
    """Stateful deterministic robot model driven by a :class:`ManualClock`."""

    def __init__(
        self,
        config: SimulationConfig | None = None,
        clock: ManualClock | None = None,
    ) -> None:
        self.config = config or SimulationConfig()
        self.clock = clock or ManualClock()
        now = self.clock.now()
        self._pose = self.config.initial_pose
        self._velocity = RobotPose()
        self._movement_state = MovementState.IDLE
        self._homed = False
        self._fault: FaultState | None = None
        self._active_command: _ActiveCommand | None = None
        self._command_history: list[RobotCommand] = []
        self._next_command_id = 0
        self._speed_scale = 1.0
        self._last_update_at = now
        self._created_at = now
        self._command_issued_at: float | None = None
        self._movement_started_at: float | None = None
        self._movement_stopped_at: float | None = None
        self._command_completed_at: float | None = None

    def advance(self, seconds: float) -> RobotState:
        """Advance simulated time and return the resulting state."""

        self.clock.advance(seconds)
        return self.get_state()

    def get_state(self) -> RobotState:
        self._synchronize()
        return RobotState(
            pose=self._pose,
            movement_state=self._movement_state,
            velocity=self._velocity,
            movement_limits=self.config.limits,
            homed=self._homed,
            current_command=(
                self._active_command.snapshot() if self._active_command else None
            ),
            fault=self._fault,
            timestamps=RobotTimestamps(
                created_at=self._created_at,
                updated_at=self.clock.now(),
                command_issued_at=self._command_issued_at,
                movement_started_at=self._movement_started_at,
                movement_stopped_at=self._movement_stopped_at,
                command_completed_at=self._command_completed_at,
            ),
        )

    @property
    def command_history(self) -> tuple[RobotCommand, ...]:
        self._synchronize()
        return tuple(self._command_history)

    def set_speed(self, speed: int) -> None:
        if speed not in range(256):
            raise ValueError("speed must be between 0 and 255")
        self._speed_scale = speed / 255.0

    def get_speed(self) -> int:
        return round(self._speed_scale * 255)

    def home(self, delay_ms: int = 0) -> int:
        self._homed = False
        return self.move_to(
            self.config.home_pose,
            delay=max(0, delay_ms) / 1000.0,
            kind=CommandKind.HOME,
            speeds=self.config.homing_speed,
        )

    def move_by(
        self,
        delta: RobotPose,
        *,
        delay: float = 0.0,
        duration: float | None = None,
    ) -> int:
        self._synchronize()
        return self.move_to(
            _pose_add(self._pose, delta), delay=delay, duration=duration
        )

    def move_to(
        self,
        target: RobotPose,
        *,
        delay: float = 0.0,
        duration: float | None = None,
        kind: CommandKind = CommandKind.MOVE_TO,
        speeds: RobotPose | None = None,
    ) -> int:
        self._validate_timing(delay, duration)
        self._synchronize()
        command_id = self._allocate_command_id()
        now = self.clock.now()
        if self._fault is not None:
            raise RuntimeError("cannot move while the robot is faulted")
        if not self.config.limits.contains(target):
            self._reject_for_limit(command_id, kind, target, now)
            return command_id

        self._preempt_current(now)
        start_at = now + self.config.command_latency + delay
        command = _ActiveCommand(
            command_id=command_id,
            kind=kind,
            status=CommandStatus.PENDING,
            issued_at=now,
            starts_at=start_at,
            target=target,
            start_pose=self._pose,
        )
        movement_speed = speeds or self.config.speed
        natural_duration = self._duration_to(target, movement_speed)
        command_duration = max(natural_duration, duration or 0.0)
        if command_duration > 0:
            command.velocity = _pose_from_values(
                {
                    axis: (getattr(target, axis) - getattr(self._pose, axis))
                    / command_duration
                    for axis in AXES
                }
            )
        command.movement_ends_at = start_at + command_duration
        self._activate_pending(command)
        return command_id

    def start_continuous(self, direction: RobotPose) -> int:
        for axis in AXES:
            if getattr(direction, axis) not in (-1, 0, 1):
                raise ValueError("continuous directions must be -1, 0, or 1")
        self._synchronize()
        if self._fault is not None:
            raise RuntimeError("cannot move while the robot is faulted")
        now = self.clock.now()
        self._preempt_current(now)
        command_id = self._allocate_command_id()
        command = _ActiveCommand(
            command_id=command_id,
            kind=CommandKind.CONTINUOUS,
            status=CommandStatus.PENDING,
            issued_at=now,
            starts_at=now + self.config.command_latency,
            direction=direction,
            start_pose=self._pose,
            velocity=_pose_from_values(
                {
                    axis: getattr(direction, axis)
                    * getattr(self.config.speed, axis)
                    * self._speed_scale
                    for axis in AXES
                }
            ),
        )
        self._activate_pending(command)
        return command_id

    def stop(self) -> None:
        """Stop and cancel the current command, applying configured settling time."""

        self._synchronize()
        now = self.clock.now()
        if self._active_command is None:
            self._movement_stopped_at = now
            self._movement_state = MovementState.IDLE
            self._velocity = RobotPose()
            return
        self._active_command.status = CommandStatus.CANCELED
        self._velocity = RobotPose()
        self._movement_stopped_at = now
        if self.config.settling_time > 0:
            self._movement_state = MovementState.SETTLING
            self._active_command.settling_ends_at = now + self.config.settling_time
        else:
            self._finish_current(now)

    def cancel(self) -> None:
        self.stop()

    def inject_fault(self, code: str, message: str) -> None:
        self._synchronize()
        now = self.clock.now()
        self._preempt_current(now)
        self._fault = FaultState(code=code, message=message, timestamp=now)
        self._movement_state = MovementState.FAULTED
        self._velocity = RobotPose()
        self._movement_stopped_at = now

    def clear_fault(self) -> None:
        self._synchronize()
        self._fault = None
        self._active_command = None
        self._movement_state = MovementState.IDLE
        self._velocity = RobotPose()

    def _activate_pending(self, command: _ActiveCommand) -> None:
        self._active_command = command
        self._command_issued_at = command.issued_at
        self._movement_state = MovementState.WAITING
        self._velocity = RobotPose()
        self._last_update_at = command.issued_at
        self._synchronize()

    def _synchronize(self) -> None:
        now = self.clock.now()
        if now < self._last_update_at:
            raise RuntimeError("simulation clock moved backwards")
        command = self._active_command
        if command is None or self._fault is not None:
            self._last_update_at = now
            return

        if command.status == CommandStatus.PENDING:
            if now < command.starts_at:
                self._movement_state = MovementState.WAITING
                self._velocity = RobotPose()
                self._last_update_at = now
                return
            self._movement_started_at = command.starts_at
            command.status = CommandStatus.ACTIVE
            self._movement_state = (
                MovementState.HOMING
                if command.kind == CommandKind.HOME
                else MovementState.MOVING
            )
            self._velocity = command.velocity
            self._last_update_at = command.starts_at

        if self._movement_state == MovementState.SETTLING:
            settle_end = command.settling_ends_at or self._last_update_at
            if now >= settle_end:
                self._finish_current(settle_end)
            self._last_update_at = now
            return

        if command.kind == CommandKind.CONTINUOUS:
            self._advance_continuous(now)
            return

        movement_end = command.movement_ends_at or command.starts_at
        if now < movement_end:
            elapsed = now - command.starts_at
            self._pose = _pose_add(
                command.start_pose or self._pose,
                _pose_scale(command.velocity, elapsed),
            )
            self._velocity = command.velocity
            self._last_update_at = now
            return

        self._pose = command.target or self._pose
        self._velocity = RobotPose()
        self._movement_stopped_at = movement_end
        if command.kind == CommandKind.HOME:
            self._homed = True
        if self.config.settling_time > 0:
            command.status = CommandStatus.SETTLING
            command.settling_ends_at = movement_end + self.config.settling_time
            self._movement_state = MovementState.SETTLING
            if now >= command.settling_ends_at:
                self._finish_current(command.settling_ends_at)
        else:
            self._finish_current(movement_end)
        self._last_update_at = now

    def _advance_continuous(self, now: float) -> None:
        command = self._active_command
        if command is None:
            return
        elapsed = now - self._last_update_at
        hit_after: float | None = None
        hit_axis: str | None = None
        for axis in AXES:
            velocity = getattr(command.velocity, axis)
            if velocity == 0:
                continue
            limit = self.config.limits.for_axis(axis)
            boundary = limit.maximum if velocity > 0 else limit.minimum
            time_to_boundary = (boundary - getattr(self._pose, axis)) / velocity
            if 0 <= time_to_boundary <= elapsed and (
                hit_after is None or time_to_boundary < hit_after
            ):
                hit_after = time_to_boundary
                hit_axis = axis

        travel_time = elapsed if hit_after is None else hit_after
        self._pose = _pose_add(self._pose, _pose_scale(command.velocity, travel_time))
        self._last_update_at = now
        if hit_axis is None:
            self._velocity = command.velocity
            return

        fault_time = now - elapsed + travel_time
        command.status = CommandStatus.REJECTED
        self._command_history.append(command.snapshot())
        self._fault = FaultState(
            code="movement_limit",
            message=f"continuous movement reached the {hit_axis} limit",
            timestamp=fault_time,
        )
        self._movement_state = MovementState.FAULTED
        self._velocity = RobotPose()
        self._movement_stopped_at = fault_time

    def _duration_to(self, target: RobotPose, speeds: RobotPose) -> float:
        durations: list[float] = []
        for axis in AXES:
            distance = abs(getattr(target, axis) - getattr(self._pose, axis))
            speed = getattr(speeds, axis) * self._speed_scale
            if distance > 0 and speed <= 0:
                raise ValueError(f"{axis} speed must be positive for this movement")
            durations.append(distance / speed if distance > 0 else 0.0)
        return max(durations)

    def _preempt_current(self, timestamp: float) -> None:
        if self._active_command is None:
            return
        if self._active_command.status not in (
            CommandStatus.COMPLETED,
            CommandStatus.CANCELED,
            CommandStatus.REJECTED,
        ):
            self._active_command.status = CommandStatus.CANCELED
            self._command_history.append(self._active_command.snapshot())
        self._active_command = None
        self._velocity = RobotPose()
        self._movement_stopped_at = timestamp

    def _finish_current(self, timestamp: float) -> None:
        command = self._active_command
        if command is not None:
            if command.status != CommandStatus.CANCELED:
                command.status = CommandStatus.COMPLETED
            self._command_history.append(command.snapshot())
        self._active_command = None
        self._movement_state = MovementState.IDLE
        self._velocity = RobotPose()
        self._command_completed_at = timestamp

    def _reject_for_limit(
        self,
        command_id: int,
        kind: CommandKind,
        target: RobotPose,
        timestamp: float,
    ) -> None:
        self._preempt_current(timestamp)
        command = _ActiveCommand(
            command_id=command_id,
            kind=kind,
            status=CommandStatus.REJECTED,
            issued_at=timestamp,
            starts_at=timestamp,
            target=target,
        )
        self._active_command = command
        self._command_history.append(command.snapshot())
        self._fault = FaultState(
            code="movement_limit",
            message="target pose is outside movement limits",
            timestamp=timestamp,
        )
        self._movement_state = MovementState.FAULTED
        self._velocity = RobotPose()
        self._command_issued_at = timestamp

    def _allocate_command_id(self) -> int:
        command_id = self._next_command_id
        self._next_command_id += 1
        return command_id

    @staticmethod
    def _validate_timing(delay: float, duration: float | None) -> None:
        if not math.isfinite(delay) or delay < 0:
            raise ValueError("delay must be finite and non-negative")
        if duration is not None and (not math.isfinite(duration) or duration < 0):
            raise ValueError("duration must be finite and non-negative")
