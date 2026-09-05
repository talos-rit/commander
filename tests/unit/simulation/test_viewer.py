import inspect

import pytest

pytest.importorskip("pybullet")

from src.robot_state import (  # noqa: E402
    MappingQuality,
    RobotStateSnapshot,
    StateSourceType,
)
from src.simulation.viewer import (  # noqa: E402
    LEGACY_URDF,
    PyBulletRobotViewer,
    RobotVisualConfig,
)
from src.simulation import (  # noqa: E402
    SimulatedRobot,
    SimulatedRobotStateSource,
    legacy_visual_mapping,
)


def snapshot(robot_id: str, **positions: float) -> RobotStateSnapshot:
    return RobotStateSnapshot(
        robot_id=robot_id,
        timestamp=1.0,
        source_type=StateSourceType.SIMULATED,
        joint_positions=positions or None,
        joint_mapping_quality=(
            MappingQuality.LEGACY_APPROXIMATION
            if positions
            else MappingQuality.UNKNOWN
        ),
    )


def test_legacy_urdf_loads_and_joints_are_resolved_by_name() -> None:
    with PyBulletRobotViewer(gui=False) as viewer:
        viewer.add_robot(RobotVisualConfig("bluey", LEGACY_URDF))

        positions = viewer.get_joint_positions("bluey")

    assert "base_joint" in positions
    assert "pitch_joint" in positions
    assert len(positions) == 7


def test_two_robots_are_independent() -> None:
    with PyBulletRobotViewer(gui=False) as viewer:
        viewer.add_robot(RobotVisualConfig("a", base_position=(-0.5, 0, 0)))
        viewer.add_robot(RobotVisualConfig("b", base_position=(0.5, 0, 0)))
        b_before = viewer.get_joint_positions("b")

        viewer.update(snapshot("a", base_joint=0.75))

        assert viewer.get_joint_positions("a")["base_joint"] == pytest.approx(0.75)
        assert viewer.get_joint_positions("b") == b_before


def test_unknown_state_does_not_become_fake_joint_state() -> None:
    with PyBulletRobotViewer(gui=False) as viewer:
        viewer.add_robot(RobotVisualConfig("bluey"))
        viewer.update(snapshot("bluey", base_joint=0.4))

        viewer.update(snapshot("bluey"))

        assert viewer.get_joint_positions("bluey")["base_joint"] == pytest.approx(0.4)


def test_viewer_has_no_publisher_or_command_dependency() -> None:
    constructor = inspect.signature(PyBulletRobotViewer)

    assert "publisher" not in constructor.parameters
    assert not any(
        name in vars(PyBulletRobotViewer)
        for name in ("home", "move_to", "stop", "set_speed")
    )


def test_viewer_update_does_not_mutate_source_simulator() -> None:
    source_robot = SimulatedRobot()
    source = SimulatedRobotStateSource(
        "bluey", source_robot, legacy_visual_mapping()
    )
    before = source_robot.get_state()

    with PyBulletRobotViewer(gui=False) as viewer:
        viewer.add_robot(RobotVisualConfig("bluey"))
        viewer.update(source.get_snapshot())
        viewer.step()

    assert source_robot.get_state() == before
