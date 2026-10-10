from io import StringIO

import pytest

from src.robot_state import MappingQuality, StateSourceType
from src.simulation import (
    RobotPose,
    LegacyPyBulletIKMapper,
    Scenario,
    ScenarioAction,
    ScenarioEvent,
    ScenarioRunner,
    SimulatedPublisher,
    SimulatedRobot,
    SimulatedRobotStateSource,
    TrajectoryRecorder,
    TrajectoryReplay,
    legacy_visual_mapping,
)


def test_unmapped_logical_state_remains_explicitly_unknown() -> None:
    robot = SimulatedRobot()
    source = SimulatedRobotStateSource("bluey", robot)

    snapshot = source.get_snapshot()

    assert snapshot.source_type == StateSourceType.SIMULATED
    assert snapshot.logical_pose is not None
    assert snapshot.joint_positions is None
    assert snapshot.joint_velocities is None
    assert snapshot.joint_mapping_quality == MappingQuality.UNKNOWN


def test_legacy_mapping_is_named_and_labeled_approximate() -> None:
    robot = SimulatedRobot()
    robot.move_to(RobotPose(azimuth=10.0), duration=1.0)
    robot.advance(0.5)

    snapshot = SimulatedRobotStateSource(
        "bluey", robot, legacy_visual_mapping()
    ).get_snapshot()

    assert snapshot.joint_mapping_quality == MappingQuality.LEGACY_APPROXIMATION
    assert snapshot.joint_positions is not None
    assert "base_joint" in snapshot.joint_positions
    assert "pitch_joint" in snapshot.joint_positions
    assert robot.get_state().pose.azimuth == 5.0


def test_scenario_is_repeatable_and_uses_publisher_commands() -> None:
    scenario = Scenario(
        events=(
            ScenarioEvent(
                0.0,
                ScenarioAction.POLAR_CONTINUOUS,
                {"azimuth": 1, "altitude": 0},
            ),
            ScenarioEvent(0.5, ScenarioAction.SET_SPEED, {"speed": 128}),
            ScenarioEvent(1.0, ScenarioAction.STOP),
        ),
        duration=1.5,
    )

    def run():
        robot = SimulatedRobot()
        publisher = SimulatedPublisher(robot)
        source = SimulatedRobotStateSource("bluey", robot)
        return ScenarioRunner(publisher, source, timestep=0.25).run(scenario)

    assert run() == run()


def test_trajectory_round_trip_preserves_order_and_timestamps() -> None:
    robot = SimulatedRobot()
    source = SimulatedRobotStateSource("bluey", robot, legacy_visual_mapping())
    snapshots = [source.get_snapshot()]
    robot.start_continuous(RobotPose(azimuth=1.0))
    snapshots.extend(source.get_snapshot() for _ in range(1))
    robot.advance(0.25)
    snapshots.append(source.get_snapshot())

    output = StringIO()
    recorder = TrajectoryRecorder(output)
    for snapshot in snapshots:
        recorder.record(snapshot)

    output.seek(0)
    replay = TrajectoryReplay.from_jsonl(output)

    assert tuple(replay) == tuple(snapshots)
    assert [state.timestamp for state in replay] == [0.0, 0.0, 0.25]
    assert list(replay) == list(replay)


def test_state_adapter_does_not_mutate_source_simulator() -> None:
    robot = SimulatedRobot()
    before = robot.get_state()

    snapshot = SimulatedRobotStateSource(
        "bluey", robot, legacy_visual_mapping()
    ).get_snapshot()

    assert robot.get_state() == before
    assert snapshot.logical_pose is not before.pose


def test_legacy_ik_mapping_visually_moves_cartesian_endpoint() -> None:
    pytest.importorskip("pybullet")
    with LegacyPyBulletIKMapper() as mapper:
        home = mapper.map_positions(RobotPose())
        moved = mapper.map_positions(RobotPose(y=100.0, z=100.0))

    assert moved["shoulder_joint"] != pytest.approx(home["shoulder_joint"])
    assert moved["elbow_joint"] != pytest.approx(home["elbow_joint"])
    assert mapper.quality == MappingQuality.LEGACY_APPROXIMATION
