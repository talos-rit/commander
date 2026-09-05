"""Interactive simulation controls kept separate from the state-only renderer."""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import replace
from dataclasses import dataclass
from typing import Protocol

from src.robot_state import RobotStateSnapshot, RobotStateSource, StateSourceType

from .publisher import SimulatedPublisher
from .robot import RobotPose


KEYBOARD_HELP_TEXT = (
    "A / D      rotate robot left / right (hold)\n"
    "W / S      extend / retract arm (hold, approximate IK)\n"
    "J / K      tilt camera head up / down\n"
    "H          home selected robot\n"
    "Space / X  stop selected robot\n"
    "+ / -      increase / decrease speed\n"
    "1 / 2 / 3  move to target preset\n"
    "Tab        select next robot\n"
    "P          print telemetry"
)


class InteractiveViewer(Protocol):
    def get_keyboard_events(self) -> Mapping[int, int]: ...

    def update(self, snapshot: RobotStateSnapshot) -> None: ...

    def step(self, seconds: float | None = None) -> None: ...

    def is_connected(self) -> bool: ...


class RobotCommandTarget(Protocol):
    """Shared command surface implemented by real and simulated Publishers."""

    def home(self, delay_ms: int): ...

    def is_connected(self) -> bool: ...

    def set_speed(self, speed: int): ...

    def polar_pan_continuous_start(self, azimuth: int, altitude: int): ...

    def polar_pan_continuous_stop(self): ...

    def cartesian_move_continuous_start(self, x: int, y: int, z: int): ...

    def cartesian_move_continuous_stop(self): ...

    def polar_pan_discrete(
        self, azimuth: int, altitude: int, delay_ms: int, duration_ms: int
    ): ...

    def cartesian_move_discrete(
        self, x: int, y: int, z: int, delay_ms: int, duration_ms: int
    ): ...


class InteractiveControlPanel(Protocol):
    def poll(self, snapshots: tuple[RobotStateSnapshot, ...]) -> bool: ...

    def close(self) -> None: ...


@dataclass(frozen=True)
class KeyboardFlags:
    is_down: int
    was_triggered: int


class InteractiveSimulationController:
    """Turn keyboard input into normal Publisher calls for multiple simulators."""

    def __init__(
        self,
        publishers: Mapping[str, SimulatedPublisher],
        state_sources: Mapping[str, RobotStateSource],
        viewer: InteractiveViewer,
        keyboard_flags: KeyboardFlags,
        *,
        timestep: float = 1 / 60,
        real_publishers: Mapping[str, RobotCommandTarget] | None = None,
    ) -> None:
        if not publishers or set(publishers) != set(state_sources):
            raise ValueError(
                "publishers and state sources must have matching robot IDs"
            )
        if timestep <= 0:
            raise ValueError("timestep must be positive")
        self.publishers = dict(publishers)
        self.real_publishers = dict(real_publishers or {})
        unknown_real_ids = set(self.real_publishers) - set(self.publishers)
        if unknown_real_ids:
            raise ValueError(
                "real publishers have no matching simulator: "
                f"{sorted(unknown_real_ids)}"
            )
        self.state_sources = dict(state_sources)
        self.viewer = viewer
        self.flags = keyboard_flags
        self.timestep = timestep
        self.robot_ids = tuple(self.publishers)
        self.selected_index = 0
        self._backend_modes = {robot_id: "virtual" for robot_id in self.robot_ids}
        self._continuous_kind: str | None = None
        self._continuous_direction: tuple[int, ...] = ()
        self._keyboard_continuous_active = False
        self.last_error: dict[str, str | None] = {
            robot_id: None for robot_id in self.robot_ids
        }

    @property
    def selected_robot_id(self) -> str:
        return self.robot_ids[self.selected_index]

    @property
    def selected_backend(self) -> str:
        return self._backend_modes[self.selected_robot_id]

    def available_backends(self, robot_id: str | None = None) -> tuple[str, ...]:
        robot_id = robot_id or self.selected_robot_id
        return (
            ("virtual", "real")
            if self.real_backend_connected(robot_id)
            else ("virtual",)
        )

    def real_backend_connected(self, robot_id: str | None = None) -> bool:
        robot_id = robot_id or self.selected_robot_id
        publisher = self.real_publishers.get(robot_id)
        if publisher is None:
            return False
        check = getattr(publisher, "is_connected", None)
        return True if check is None else bool(check())

    def set_selected_backend(self, backend: str) -> None:
        if backend not in self.available_backends():
            raise ValueError(
                f"backend {backend!r} is unavailable for {self.selected_robot_id}"
            )
        if backend == self.selected_backend:
            return
        self.stop_selected()
        self._backend_modes[self.selected_robot_id] = backend
        print(f"{self.selected_robot_id}: backend={backend.upper()}")

    def process_keyboard(self, events: Mapping[int, int]) -> None:
        if self._triggered(events, "\t"):
            self._stop_continuous()
            self.selected_index = (self.selected_index + 1) % len(self.robot_ids)
            print(f"Selected robot: {self.selected_robot_id}")

        if self._triggered(events, "h"):
            self.home_selected()
        if self._triggered(events, " ") or self._triggered(events, "x"):
            self.stop_selected()
        if self._triggered(events, "+") or self._triggered(events, "="):
            self._change_speed(25)
        if self._triggered(events, "-"):
            self._change_speed(-25)
        if self._triggered(events, "j"):
            self.move_polar_discrete(0, 10)
        if self._triggered(events, "k"):
            self.move_polar_discrete(0, -10)
        if self._triggered(events, "1"):
            self.move_to_preset(1)
        if self._triggered(events, "2"):
            self.move_to_preset(2)
        if self._triggered(events, "3"):
            self.move_to_preset(3)
        if self._triggered(events, "p"):
            self.print_telemetry()

        azimuth = int(self._held(events, "d")) - int(self._held(events, "a"))
        extension = int(self._held(events, "w")) - int(self._held(events, "s"))
        if azimuth:
            direction = (azimuth, 0)
            if (
                direction != self._continuous_direction
                or self._continuous_kind != "polar"
            ):
                self.start_polar_continuous(*direction)
            self._keyboard_continuous_active = True
        elif extension:
            # The legacy model's home endpoint lies primarily along negative Y.
            # W therefore moves Y- (away) and S moves Y+ (toward the base). The
            # state remains a normal Cartesian Publisher command; only the viewer
            # uses approximate IK to display it.
            direction = (0, -extension, 0)
            if (
                direction != self._continuous_direction
                or self._continuous_kind != "cartesian"
            ):
                self.start_cartesian_continuous(*direction)
            self._keyboard_continuous_active = True
        elif self._keyboard_continuous_active:
            self._stop_continuous()

    def advance_once(self) -> tuple[RobotStateSnapshot, ...]:
        snapshots = []
        for robot_id, publisher in self.publishers.items():
            publisher.advance(self.timestep)
            snapshot = self.state_sources[robot_id].get_snapshot()
            if self._backend_modes[robot_id] == "real":
                snapshot = replace(
                    snapshot, source_type=StateSourceType.COMMAND_ESTIMATE
                )
            self.viewer.update(snapshot)
            snapshots.append(snapshot)
        self.viewer.step(self.timestep)
        return tuple(snapshots)

    def select_robot(self, robot_id: str) -> None:
        if robot_id not in self.publishers:
            raise KeyError(f"unknown robot: {robot_id}")
        self._stop_continuous()
        self.selected_index = self.robot_ids.index(robot_id)
        print(f"Selected robot: {self.selected_robot_id}")

    def home_selected(self) -> int | None:
        self._clear_continuous_state()
        command_id = self._invoke("home", 0)
        print(f"{self.selected_robot_id}: home command {command_id}")
        return command_id

    def stop_selected(self) -> None:
        self._invoke("polar_pan_continuous_stop")
        self._invoke("cartesian_move_continuous_stop")
        self._clear_continuous_state()
        print(f"{self.selected_robot_id}: stop")

    def clear_selected_simulation_fault(self) -> None:
        robot_id = self.selected_robot_id
        self.publishers[robot_id].clear_fault()
        self.last_error[robot_id] = None
        self._clear_continuous_state()
        print(f"{robot_id}: simulation fault cleared")

    def set_selected_speed(self, speed: int) -> None:
        self._invoke("set_speed", speed)
        if self._continuous_kind == "polar":
            self._invoke("polar_pan_continuous_start", *self._continuous_direction)
        elif self._continuous_kind == "cartesian":
            self._invoke(
                "cartesian_move_continuous_start", *self._continuous_direction
            )
        print(f"{self.selected_robot_id}: speed={speed}")

    def get_selected_speed(self) -> int:
        return self.publishers[self.selected_robot_id].get_speed()

    def start_polar_continuous(
        self, azimuth: int, altitude: int
    ) -> int | None:
        command_id = self._invoke(
            "polar_pan_continuous_start", azimuth, altitude
        )
        if command_id is not None:
            self._continuous_kind = "polar"
            self._continuous_direction = (azimuth, altitude)
        return command_id

    def start_cartesian_continuous(
        self, x: int, y: int, z: int
    ) -> int | None:
        command_id = self._invoke("cartesian_move_continuous_start", x, y, z)
        if command_id is not None:
            self._continuous_kind = "cartesian"
            self._continuous_direction = (x, y, z)
        return command_id

    def stop_continuous(self) -> None:
        self._stop_continuous()

    def move_polar_discrete(self, azimuth: int, altitude: int) -> int | None:
        self._clear_continuous_state()
        return self._invoke(
            "polar_pan_discrete", azimuth, altitude, 0, 500
        )

    def move_cartesian_discrete(self, x: int, y: int, z: int) -> int | None:
        self._clear_continuous_state()
        return self._invoke(
            "cartesian_move_discrete", x, y, z, 0, 500
        )

    def move_to_preset(self, preset: int) -> int | None:
        targets = {
            1: RobotPose(azimuth=-35.0, altitude=0.0),
            2: RobotPose(),
            3: RobotPose(azimuth=35.0, altitude=15.0),
        }
        if preset not in targets:
            raise ValueError("preset must be 1, 2, or 3")
        if self.selected_backend == "real":
            print(f"{self.selected_robot_id}: presets unavailable in REAL mode")
            return None
        self._clear_continuous_state()
        return self.publishers[self.selected_robot_id].move_to(targets[preset])

    def run(self, control_panel: InteractiveControlPanel | None = None) -> None:
        print_interactive_help()
        print(f"Selected robot: {self.selected_robot_id}")
        try:
            while self.viewer.is_connected():
                started = time.perf_counter()
                self.process_keyboard(self.viewer.get_keyboard_events())
                snapshots = self.advance_once()
                if control_panel is not None and not control_panel.poll(snapshots):
                    break
                remaining = self.timestep - (time.perf_counter() - started)
                if remaining > 0:
                    time.sleep(remaining)
        except KeyboardInterrupt:
            pass
        finally:
            if control_panel is not None:
                control_panel.close()
            self.stop_all_real()

    def stop_all_real(self) -> None:
        """Best-effort network stop; this is not a physical emergency stop."""

        for robot_id, publisher in self.real_publishers.items():
            for method_name in (
                "polar_pan_continuous_stop",
                "cartesian_move_continuous_stop",
            ):
                try:
                    getattr(publisher, method_name)()
                except OSError as error:
                    print(f"{robot_id}: real stop failed: {error}")

    def print_telemetry(self) -> None:
        for robot_id, source in self.state_sources.items():
            state = source.get_snapshot()
            pose = state.logical_pose
            pose_text = (
                "unknown"
                if pose is None
                else (
                    f"az={pose.azimuth:.2f}, alt={pose.altitude:.2f}, "
                    f"xyz=({pose.x:.2f}, {pose.y:.2f}, {pose.z:.2f})"
                )
            )
            command = (
                "none"
                if state.current_command is None
                else (
                    f"{state.current_command.command_id}:"
                    f"{state.current_command.kind}/{state.current_command.status}"
                )
            )
            print(
                f"{robot_id} t={state.timestamp:.3f} state={state.movement_state} "
                f"pose=[{pose_text}] homed={state.homed} command={command} "
                f"fault={state.fault}"
            )

    def _change_speed(self, delta: int) -> None:
        speed = min(255, max(0, self.get_selected_speed() + delta))
        self.set_selected_speed(speed)

    def _stop_continuous(self) -> None:
        if self._continuous_kind == "polar":
            self._invoke("polar_pan_continuous_stop")
        elif self._continuous_kind == "cartesian":
            self._invoke("cartesian_move_continuous_stop")
        self._clear_continuous_state()

    def _invoke(self, method_name: str, *args):
        robot_id = self.selected_robot_id
        simulation_method = getattr(self.publishers[robot_id], method_name)
        real_command_sent = False
        if self._backend_modes[robot_id] == "real":
            real_method = getattr(self.real_publishers[robot_id], method_name)
            real_method(*args)
            real_command_sent = True
        try:
            result = simulation_method(*args)
        except RuntimeError as error:
            prefix = (
                "command estimate unavailable"
                if real_command_sent
                else "command rejected"
            )
            self.last_error[robot_id] = f"{prefix}: {error}"
            print(f"{robot_id}: {self.last_error[robot_id]}")
            # A real command may already be in flight.  Return a non-None marker so
            # press-and-hold state is retained and ButtonRelease still sends STOP.
            return True if real_command_sent else None
        self.last_error[robot_id] = None
        return result if result is not None else (True if real_command_sent else None)

    def _clear_continuous_state(self) -> None:
        self._continuous_kind = None
        self._continuous_direction = ()
        self._keyboard_continuous_active = False

    def _triggered(self, events: Mapping[int, int], character: str) -> bool:
        return any(
            events.get(code, 0) & self.flags.was_triggered
            for code in self._character_codes(character)
        )

    def _held(self, events: Mapping[int, int], character: str) -> bool:
        return any(
            events.get(code, 0) & self.flags.is_down
            for code in self._character_codes(character)
        )

    @staticmethod
    def _character_codes(character: str) -> tuple[int, ...]:
        codes = {ord(character)}
        if character.isalpha():
            codes.add(ord(character.swapcase()))
        return tuple(codes)


def print_interactive_help() -> None:
    print(f"Robot controls:\n{KEYBOARD_HELP_TEXT}")
