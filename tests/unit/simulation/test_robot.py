from types import SimpleNamespace

import pytest

import src.config as config
from src.connection.connection import Connection
from src.connection.publisher import Direction, Publisher
from src.simulation import (
    AxisLimits,
    CommandStatus,
    MovementState,
    RobotLimits,
    RobotPose,
    SimulationConfig,
    SimulatedPublisher,
    SimulatedRobot,
)
from src.talos_app import ContinuousDirector


def make_config(**overrides) -> SimulationConfig:
    values = {
        "speed": RobotPose(azimuth=10.0, altitude=10.0, x=20.0, y=20.0, z=20.0),
        "homing_speed": RobotPose(
            azimuth=5.0, altitude=5.0, x=10.0, y=10.0, z=10.0
        ),
        "command_latency": 0.5,
        "settling_time": 0.25,
    }
    values.update(overrides)
    return SimulationConfig(**values)


def test_target_move_obeys_latency_speed_and_settling() -> None:
    robot = SimulatedRobot(make_config())

    command_id = robot.move_to(RobotPose(azimuth=20.0))
    assert command_id == 0
    assert robot.get_state().movement_state == MovementState.WAITING

    state = robot.advance(0.25)
    assert state.pose.azimuth == 0.0
    assert state.velocity.azimuth == 0.0
    assert state.timestamps.updated_at == 0.25

    state = robot.advance(0.25)
    assert state.movement_state == MovementState.MOVING
    assert state.velocity.azimuth == 10.0
    assert state.timestamps.movement_started_at == 0.5

    state = robot.advance(1.0)
    assert state.pose.azimuth == pytest.approx(10.0)

    state = robot.advance(1.0)
    assert state.pose.azimuth == 20.0
    assert state.movement_state == MovementState.SETTLING
    assert state.current_command is not None
    assert state.current_command.status == CommandStatus.SETTLING

    state = robot.advance(0.25)
    assert state.movement_state == MovementState.IDLE
    assert state.current_command is None
    assert state.timestamps.command_completed_at == 2.75
    assert robot.command_history[-1].status == CommandStatus.COMPLETED


def test_identical_command_sequences_are_deterministic() -> None:
    def run_sequence() -> tuple:
        robot = SimulatedRobot(make_config())
        robot.move_by(RobotPose(azimuth=15.0, altitude=-5.0), duration=2.0)
        snapshots = [robot.advance(step) for step in (0.2, 0.3, 0.75, 0.75, 0.75, 0.25)]
        return tuple(snapshots), robot.command_history

    assert run_sequence() == run_sequence()


def test_home_moves_over_time_and_marks_robot_homed_after_arrival() -> None:
    robot = SimulatedRobot(
        make_config(
            initial_pose=RobotPose(azimuth=10.0),
            home_pose=RobotPose(),
            command_latency=0.1,
            settling_time=0.2,
        )
    )

    robot.home(delay_ms=100)
    assert robot.advance(0.2).movement_state == MovementState.HOMING
    assert robot.advance(1.0).pose.azimuth == pytest.approx(5.0)

    state = robot.advance(1.0)
    assert state.pose == RobotPose()
    assert state.homed is True
    assert state.movement_state == MovementState.SETTLING
    assert robot.advance(0.2).movement_state == MovementState.IDLE


def test_new_command_preempts_and_stop_cancels_without_teleporting() -> None:
    robot = SimulatedRobot(make_config(command_latency=0.0, settling_time=0.5))

    first_id = robot.start_continuous(RobotPose(azimuth=1.0))
    assert robot.advance(1.0).pose.azimuth == pytest.approx(10.0)

    second_id = robot.move_to(RobotPose(azimuth=0.0))
    assert second_id == first_id + 1
    assert robot.command_history[-1].command_id == first_id
    assert robot.command_history[-1].status == CommandStatus.CANCELED

    moving = robot.advance(0.5)
    assert moving.pose.azimuth == pytest.approx(5.0)
    robot.cancel()
    canceled_pose = robot.get_state().pose
    assert robot.get_state().movement_state == MovementState.SETTLING

    settled = robot.advance(0.5)
    assert settled.pose == canceled_pose
    assert settled.movement_state == MovementState.IDLE
    assert robot.command_history[-1].command_id == second_id
    assert robot.command_history[-1].status == CommandStatus.CANCELED


def test_continuous_move_stops_at_limit_and_reports_fault() -> None:
    limits = RobotLimits(azimuth=AxisLimits(-5.0, 5.0))
    robot = SimulatedRobot(
        make_config(limits=limits, command_latency=0.0, settling_time=0.0)
    )

    robot.start_continuous(RobotPose(azimuth=1.0))
    state = robot.advance(1.0)

    assert state.pose.azimuth == 5.0
    assert state.velocity == RobotPose()
    assert state.movement_state == MovementState.FAULTED
    assert state.fault is not None
    assert state.fault.code == "movement_limit"
    assert state.fault.timestamp == pytest.approx(0.5)
    assert state.current_command is not None
    assert state.current_command.status == CommandStatus.REJECTED

    robot.clear_fault()
    assert robot.get_state().movement_state == MovementState.IDLE
    assert robot.get_state().fault is None


def test_out_of_range_target_is_rejected_without_moving() -> None:
    limits = RobotLimits(azimuth=AxisLimits(-5.0, 5.0))
    robot = SimulatedRobot(make_config(limits=limits))

    command_id = robot.move_to(RobotPose(azimuth=6.0))
    state = robot.get_state()

    assert state.pose == RobotPose()
    assert state.movement_state == MovementState.FAULTED
    assert state.current_command is not None
    assert state.current_command.command_id == command_id
    assert state.current_command.status == CommandStatus.REJECTED


def test_simulated_publisher_reuses_direction_and_movement_interface() -> None:
    publisher = SimulatedPublisher(
        SimulatedRobot(make_config(command_latency=0.0, settling_time=0.0))
    )

    assert isinstance(publisher, Publisher)
    publisher.polar_pan_continuous_direction_start(Direction.LEFT)
    assert publisher.advance(0.5).pose.azimuth == pytest.approx(-5.0)

    publisher.polar_pan_continuous_stop()
    assert publisher.get_state().movement_state == MovementState.IDLE

    publisher.set_speed(128)
    assert publisher.get_speed() == 128
    publisher.cartesian_move_discrete(20, -10, 0, delay_ms=0, time=1000)
    movement_duration = 255 / 128
    halfway = publisher.advance(movement_duration / 2)
    assert halfway.pose.x == pytest.approx(10.0)
    assert halfway.pose.y == pytest.approx(-5.0)
    completed = publisher.advance(movement_duration / 2)
    assert completed.pose.azimuth == pytest.approx(-5.0)
    assert completed.pose.x == pytest.approx(20.0)
    assert completed.pose.y == pytest.approx(-10.0)


def test_connection_can_inject_simulated_publisher(monkeypatch) -> None:
    publisher = SimulatedPublisher()
    monkeypatch.setitem(config.ROBOT_CONFIGS, "sim", SimpleNamespace(manual_only=False))

    connection = Connection(
        host="sim",
        port=0,
        video_connection=None,
        publisher_factory=lambda _host, _port: publisher,
    )

    assert connection.publisher is publisher
    connection.publisher.home(0)
    assert publisher.get_state().homed is True
    connection.close()
    assert publisher.closed is True


def test_continuous_director_can_command_simulated_publisher(monkeypatch) -> None:
    publisher = SimulatedPublisher(
        SimulatedRobot(make_config(command_latency=0.0, settling_time=0.0))
    )
    monkeypatch.setitem(
        config.ROBOT_CONFIGS, "sim", SimpleNamespace(confirmation_delay=0.0)
    )
    director = ContinuousDirector.__new__(ContinuousDirector)
    director.last_command_stop = False
    director.movement_detection_start_time = None

    director.process_frame(
        hostname="sim",
        bounding_box=[(90, 40, 100, 60)],
        frame_shape=(100, 100, 3),
        publisher=publisher,
    )

    state = publisher.get_state()
    assert state.movement_state == MovementState.MOVING
    assert state.velocity.azimuth > 0
