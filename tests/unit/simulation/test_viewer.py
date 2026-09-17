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
    _wait_for_real_backend,
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


class SequencedRealBackendController:
    def __init__(self, states: list[bool]) -> None:
        self.states = iter(states)

    def real_backend_connected(self) -> bool:
        return next(self.states)


def test_wait_for_real_backend_handles_async_connection(monkeypatch) -> None:
    controller = SequencedRealBackendController([False, False, True])
    monkeypatch.setattr("src.simulation.viewer.time.sleep", lambda _seconds: None)

    assert _wait_for_real_backend(controller, timeout_seconds=1.0)


def test_wait_for_real_backend_times_out(monkeypatch) -> None:
    now = iter((0.0, 0.0, 1.0))
    controller = SequencedRealBackendController([False, False])
    monkeypatch.setattr("src.simulation.viewer.time.monotonic", lambda: next(now))
    monkeypatch.setattr("src.simulation.viewer.time.sleep", lambda _seconds: None)

    assert not _wait_for_real_backend(controller, timeout_seconds=1.0)


def test_legacy_urdf_loads_and_joints_are_resolved_by_name() -> None:
    with PyBulletRobotViewer(gui=False) as viewer:
        viewer.add_robot(RobotVisualConfig("bluey", LEGACY_URDF))

        positions = viewer.get_joint_positions("bluey")

    assert "base_joint" in positions
    assert "pitch_joint" in positions
    assert len(positions) == 7


def test_legacy_pedestal_is_level_and_on_the_pybullet_floor() -> None:
    with PyBulletRobotViewer(gui=False) as viewer:
        viewer.add_robot(RobotVisualConfig("bluey", LEGACY_URDF))
        body_id = viewer._robots["bluey"].body_id
        lower, _upper = viewer._p.getAABB(body_id, -1, physicsClientId=viewer.client_id)

    assert lower[2] == pytest.approx(0.0, abs=1e-6)


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


def test_real_measurement_outside_legacy_urdf_limit_renders_without_clipping() -> None:
    measured_elbow = 2.512909350520678
    state = RobotStateSnapshot(
        robot_id="bluey",
        timestamp=1.0,
        source_type=StateSourceType.REAL,
        joint_positions={"elbow_joint": measured_elbow},
        joint_mapping_quality=MappingQuality.UNKNOWN,
    )

    with PyBulletRobotViewer(gui=False) as viewer:
        viewer.add_robot(RobotVisualConfig("bluey"))
        viewer.update(state)

        assert viewer.get_joint_positions("bluey")["elbow_joint"] == pytest.approx(measured_elbow)


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
