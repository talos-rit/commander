"""Publisher-compatible adapter for the deterministic robot simulation."""

from __future__ import annotations

from typing import Protocol

from src.connection.publisher import Publisher

from .robot import RobotPose, RobotState, SimulatedRobot


class RobotSimulationBackend(Protocol):
    """Behavior needed by the Publisher adapter, independent of plant implementation."""

    def get_state(self) -> RobotState: ...

    def advance(self, seconds: float) -> RobotState: ...

    def cancel(self) -> None: ...

    def move_to(self, target: RobotPose, *, duration: float | None = None) -> int: ...

    def move_by(
        self,
        delta: RobotPose,
        *,
        delay: float = 0.0,
        duration: float | None = None,
    ) -> int: ...

    def start_continuous(self, direction: RobotPose) -> int: ...

    def stop(self) -> None: ...

    def home(self, delay_ms: int = 0) -> int: ...

    def set_speed(self, speed: int) -> None: ...

    def get_speed(self) -> int: ...


class SimulatedPublisher(Publisher):
    """Implements Commander's movement Publisher API without opening a socket."""

    def __init__(self, robot: RobotSimulationBackend | None = None) -> None:
        # Publisher.__init__ intentionally is not called: the simulator has no socket.
        self.robot = robot or SimulatedRobot()
        self.closed = False

    def close(self) -> None:
        self.closed = True

    def handshake(self) -> bool:
        return not self.closed

    def is_connected(self) -> bool:
        return not self.closed

    def get_state(self) -> RobotState:
        return self.robot.get_state()

    def advance(self, seconds: float) -> RobotState:
        return self.robot.advance(seconds)

    def cancel(self) -> None:
        self.robot.cancel()

    def clear_fault(self) -> None:
        clear = getattr(self.robot, "clear_fault", None)
        if clear is None:
            raise NotImplementedError("simulation backend cannot clear faults")
        clear()

    def move_to(self, target: RobotPose, duration: float | None = None) -> int:
        return self.robot.move_to(target, duration=duration)

    def polar_pan_discrete(
        self,
        delta_azimuth_int: int,
        delta_altitude_int: int,
        delay_int: int,
        duration_int: int,
    ) -> int:
        return self.robot.move_by(
            RobotPose(
                azimuth=float(delta_azimuth_int),
                altitude=float(delta_altitude_int),
            ),
            delay=delay_int / 1000.0,
            duration=duration_int / 1000.0,
        )

    def polar_pan_continuous_start(
        self, moving_azimuth_int: int = 0, moving_altitude_int: int = 0
    ) -> int:
        if moving_azimuth_int not in (-1, 0, 1) or moving_altitude_int not in (
            -1,
            0,
            1,
        ):
            raise AssertionError("continuous direction values must be -1, 0, or 1")
        return self.robot.start_continuous(
            RobotPose(
                azimuth=float(moving_azimuth_int),
                altitude=float(moving_altitude_int),
            )
        )

    def polar_pan_continuous_stop(self) -> None:
        self.robot.stop()

    def home(self, delay_ms: int) -> int:
        return self.robot.home(delay_ms)

    def set_speed(self, speed: int) -> None:
        self.robot.set_speed(speed)

    def get_speed(self) -> int:
        return self.robot.get_speed()

    def cartesian_move_discrete(
        self, delta_x: int, delta_y: int, delta_z: int, delay_ms: int, time: int
    ) -> int:
        return self.robot.move_by(
            RobotPose(x=float(delta_x), y=float(delta_y), z=float(delta_z)),
            delay=delay_ms / 1000.0,
            duration=time / 1000.0,
        )

    def cartesian_move_continuous_start(
        self, moving_x: int, moving_y: int, moving_z: int
    ) -> int:
        if any(value not in (-1, 0, 1) for value in (moving_x, moving_y, moving_z)):
            raise AssertionError("continuous direction values must be -1, 0, or 1")
        return self.robot.start_continuous(
            RobotPose(x=float(moving_x), y=float(moving_y), z=float(moving_z))
        )

    def cartesian_move_continuous_stop(self) -> None:
        self.robot.stop()
