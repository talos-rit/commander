"""Reusable PyBullet robot-state viewer and command-scenario demonstration.

The renderer is deliberately downstream of state. It receives
``RobotStateSnapshot`` values and has no Publisher reference or command methods.
"""

from __future__ import annotations

import argparse
import tempfile
import time
from contextlib import ExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from src.connection.publisher import Publisher
from src.robot_state import MappingQuality, RobotStateSnapshot

from .control_panel import TkSimulationControlPanel
from .controls import InteractiveSimulationController, KeyboardFlags
from .publisher import SimulatedPublisher
from .robot import RobotPose, SimulationConfig, SimulatedRobot
from .scenario import ScenarioRunner, demo_scenario
from .state_source import LegacyPyBulletIKMapper, SimulatedRobotStateSource
from .trajectory import TrajectoryRecorder, TrajectoryReplay


LEGACY_URDF = (
    Path(__file__).resolve().parents[2]
    / "digital_twin"
    / "sboter4u_model"
    / "robots"
    / "sboter4u_model.URDF"
)

# Bright defaults keep the untextured legacy STL geometry readable and make the
# two arms easy to distinguish. RobotVisualConfig.rgba can still override these.
DEFAULT_ROBOT_COLORS = (
    (0.12, 0.42, 0.88, 1.0),  # blue
    (0.95, 0.38, 0.08, 1.0),  # orange
    (0.20, 0.70, 0.35, 1.0),  # green (for additional/replay robots)
)


def _load_pybullet() -> Any:
    try:
        import pybullet  # type: ignore[import-not-found]
    except ImportError as error:  # pragma: no cover - depends on local environment
        raise RuntimeError(
            "PyBullet is required for the 3D viewer. Install Commander's "
            "'simulation' extra (for example: uv sync --extra simulation)."
        ) from error
    return pybullet


@dataclass(frozen=True)
class RobotVisualConfig:
    robot_id: str
    urdf_path: Path = LEGACY_URDF
    base_position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    base_orientation_rpy: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rgba: tuple[float, float, float, float] | None = None


@dataclass
class _VisualRobot:
    body_id: int
    joint_indices: dict[str, int]
    joint_limits: dict[str, tuple[float, float]]
    last_snapshot: RobotStateSnapshot | None = None
    status_text_id: int | None = None
    status_text: str | None = None


class PyBulletRobotViewer:
    """Multi-robot state renderer. It cannot issue commands by construction."""

    def __init__(self, *, gui: bool = True, timestep: float = 1 / 240) -> None:
        if timestep <= 0:
            raise ValueError("viewer timestep must be positive")
        self._p = _load_pybullet()
        self.timestep = timestep
        mode = self._p.GUI if gui else self._p.DIRECT
        self.client_id = self._p.connect(mode)
        if self.client_id < 0:
            raise RuntimeError("PyBullet connection failed")
        self.gui = gui
        self._robots: dict[str, _VisualRobot] = {}
        self._temporary_urdfs: list[tempfile.TemporaryDirectory] = []
        self._p.setTimeStep(timestep, physicsClientId=self.client_id)
        self._p.setGravity(0, 0, 0, physicsClientId=self.client_id)
        if gui:
            # The Windows ExampleBrowser clips text in its side panels. Disable that
            # chrome and draw our own grid/axes so the useful spatial reference stays.
            self._p.configureDebugVisualizer(
                self._p.COV_ENABLE_GUI, 0, physicsClientId=self.client_id
            )
            for preview_flag in (
                self._p.COV_ENABLE_RGB_BUFFER_PREVIEW,
                self._p.COV_ENABLE_DEPTH_BUFFER_PREVIEW,
                self._p.COV_ENABLE_SEGMENTATION_MARK_PREVIEW,
            ):
                self._p.configureDebugVisualizer(
                    preview_flag, 0, physicsClientId=self.client_id
                )
            self._add_reference_grid()
            self._p.resetDebugVisualizerCamera(
                cameraDistance=1.7,
                cameraYaw=45,
                cameraPitch=-25,
                cameraTargetPosition=(0.0, 0.0, 0.3),
                physicsClientId=self.client_id,
            )

    @property
    def robot_ids(self) -> tuple[str, ...]:
        return tuple(self._robots)

    def add_robot(self, config: RobotVisualConfig) -> None:
        if config.robot_id in self._robots:
            raise ValueError(f"robot already exists: {config.robot_id}")
        urdf_path = self._resolved_urdf(config.urdf_path)
        orientation = self._p.getQuaternionFromEuler(config.base_orientation_rpy)
        body_id = self._p.loadURDF(
            str(urdf_path),
            basePosition=config.base_position,
            baseOrientation=orientation,
            useFixedBase=True,
            physicsClientId=self.client_id,
        )
        joint_indices: dict[str, int] = {}
        joint_limits: dict[str, tuple[float, float]] = {}
        for index in range(
            self._p.getNumJoints(body_id, physicsClientId=self.client_id)
        ):
            info = self._p.getJointInfo(
                body_id, index, physicsClientId=self.client_id
            )
            name = info[1].decode("utf-8")
            joint_indices[name] = index
            if info[8] <= info[9]:
                joint_limits[name] = (float(info[8]), float(info[9]))
            if info[2] != self._p.JOINT_FIXED:
                self._p.setJointMotorControl2(
                    body_id,
                    index,
                    self._p.VELOCITY_CONTROL,
                    force=0,
                    physicsClientId=self.client_id,
                )
        visual = _VisualRobot(
            body_id=body_id,
            joint_indices=joint_indices,
            joint_limits=joint_limits,
        )
        color = config.rgba or DEFAULT_ROBOT_COLORS[
            len(self._robots) % len(DEFAULT_ROBOT_COLORS)
        ]
        self._robots[config.robot_id] = visual
        self._apply_color(body_id, color)

    def update(self, snapshot: RobotStateSnapshot) -> None:
        """Mirror known named joints exactly; leave all unknown joints untouched."""

        robot = self._robots.get(snapshot.robot_id)
        if robot is None:
            raise KeyError(f"robot is not loaded: {snapshot.robot_id}")
        positions = snapshot.joint_positions or {}
        velocities = snapshot.joint_velocities or {}
        unknown_names = set(positions) - set(robot.joint_indices)
        if unknown_names:
            raise KeyError(f"URDF does not contain joints: {sorted(unknown_names)}")
        for name, position in positions.items():
            limits = robot.joint_limits.get(name)
            if limits is not None and not limits[0] <= position <= limits[1]:
                raise ValueError(
                    f"{snapshot.robot_id}.{name}={position} is outside URDF limits "
                    f"[{limits[0]}, {limits[1]}]"
                )
            self._p.resetJointState(
                robot.body_id,
                robot.joint_indices[name],
                targetValue=float(position),
                targetVelocity=float(velocities.get(name, 0.0)),
                physicsClientId=self.client_id,
            )
        robot.last_snapshot = snapshot
        if self.gui:
            self._update_status_text(snapshot, robot)

    def step(self, seconds: float | None = None) -> None:
        steps = 1 if seconds is None else max(1, round(seconds / self.timestep))
        for _ in range(steps):
            self._p.stepSimulation(physicsClientId=self.client_id)

    def get_keyboard_events(self) -> Mapping[int, int]:
        if not self.gui:
            return {}
        return self._p.getKeyboardEvents(physicsClientId=self.client_id)

    def keyboard_flags(self) -> KeyboardFlags:
        return KeyboardFlags(
            is_down=self._p.KEY_IS_DOWN,
            was_triggered=self._p.KEY_WAS_TRIGGERED,
        )

    def is_connected(self) -> bool:
        return self.client_id >= 0 and bool(self._p.isConnected(self.client_id))

    def get_joint_positions(self, robot_id: str) -> Mapping[str, float]:
        robot = self._robots[robot_id]
        return {
            name: self._p.getJointState(
                robot.body_id, index, physicsClientId=self.client_id
            )[0]
            for name, index in robot.joint_indices.items()
        }

    def close(self) -> None:
        if self.client_id >= 0 and self._p.isConnected(self.client_id):
            self._p.disconnect(physicsClientId=self.client_id)
        self.client_id = -1
        for directory in self._temporary_urdfs:
            directory.cleanup()
        self._temporary_urdfs.clear()

    def __enter__(self) -> PyBulletRobotViewer:
        return self

    def __exit__(self, *_args) -> None:
        self.close()

    def _resolved_urdf(self, source: Path) -> Path:
        source = source.resolve()
        if not source.is_file():
            raise FileNotFoundError(f"Scorbot URDF was not found: {source}")
        text = source.read_text(encoding="utf-8")
        marker = "package://sboter4u_model/"
        if marker not in text:
            return source
        package_root = source.parent.parent.resolve().as_posix() + "/"
        directory = tempfile.TemporaryDirectory(prefix="commander-urdf-")
        resolved = Path(directory.name) / source.name
        resolved.write_text(text.replace(marker, package_root), encoding="utf-8")
        self._temporary_urdfs.append(directory)
        return resolved

    def _apply_color(
        self, body_id: int, rgba: tuple[float, float, float, float]
    ) -> None:
        self._p.changeVisualShape(
            body_id, -1, rgbaColor=rgba, physicsClientId=self.client_id
        )
        for index in range(
            self._p.getNumJoints(body_id, physicsClientId=self.client_id)
        ):
            self._p.changeVisualShape(
                body_id, index, rgbaColor=rgba, physicsClientId=self.client_id
            )

    def _add_reference_grid(
        self, *, half_extent: float = 2.0, spacing: float = 0.25
    ) -> None:
        """Draw a persistent world grid without the buggy ExampleBrowser panels."""

        divisions = round((half_extent * 2) / spacing)
        grid_color = (0.55, 0.55, 0.60)
        for step in range(divisions + 1):
            offset = -half_extent + step * spacing
            self._p.addUserDebugLine(
                (-half_extent, offset, 0),
                (half_extent, offset, 0),
                grid_color,
                lineWidth=1,
                physicsClientId=self.client_id,
            )
            self._p.addUserDebugLine(
                (offset, -half_extent, 0),
                (offset, half_extent, 0),
                grid_color,
                lineWidth=1,
                physicsClientId=self.client_id,
            )
        for endpoint, color in (
            ((1.0, 0.0, 0.0), (1.0, 0.1, 0.1)),
            ((0.0, 1.0, 0.0), (0.1, 1.0, 0.1)),
            ((0.0, 0.0, 1.0), (0.1, 0.2, 1.0)),
        ):
            self._p.addUserDebugLine(
                (0.0, 0.0, 0.002),
                endpoint,
                color,
                lineWidth=3,
                physicsClientId=self.client_id,
            )

    def _update_status_text(
        self, snapshot: RobotStateSnapshot, robot: _VisualRobot
    ) -> None:
        quality = {
            MappingQuality.PHYSICALLY_VALIDATED: "VALIDATED",
            MappingQuality.LEGACY_APPROXIMATION: "APPROX",
            MappingQuality.UNKNOWN: "UNMAPPED",
        }[snapshot.joint_mapping_quality]
        source = {
            "simulated": "SIM",
            "real": "REAL",
            "replay": "REPLAY",
            "command_estimate": "ESTIMATE",
        }[snapshot.source_type.value]
        movement = snapshot.movement_state or "unknown"
        message = f"{snapshot.robot_id}: {movement} [{source}/{quality}]"
        if message == robot.status_text:
            return
        if robot.status_text_id is not None:
            self._p.removeUserDebugItem(
                robot.status_text_id, physicsClientId=self.client_id
            )
        robot.status_text_id = self._p.addUserDebugText(
            message,
            (0.0, 0.0, 0.72),
            textSize=0.9,
            textColorRGB=(1.0, 0.8, 0.1)
            if snapshot.joint_mapping_quality
            != MappingQuality.PHYSICALLY_VALIDATED
            else (0.2, 1.0, 0.2),
            parentObjectUniqueId=robot.body_id,
            physicsClientId=self.client_id,
        )
        robot.status_text = message


def _run_demo(args: argparse.Namespace) -> None:
    config = SimulationConfig(
        initial_pose=RobotPose(azimuth=20.0, altitude=-10.0),
        speed=RobotPose(
            azimuth=30.0,
            altitude=30.0,
            x=1000.0,
            y=1000.0,
            z=1000.0,
        ),
        command_latency=0.35,
        settling_time=0.3,
    )
    robot = SimulatedRobot(config)
    publisher = SimulatedPublisher(robot)
    publishers = {"bluey": publisher}
    with ExitStack() as stack:
        bluey_mapper = stack.enter_context(LegacyPyBulletIKMapper())
        source = SimulatedRobotStateSource("bluey", robot, bluey_mapper)
        sources = {"bluey": source}
        viewer = stack.enter_context(PyBulletRobotViewer(gui=not args.headless))
        if not args.headless:
            _print_camera_help()
        viewer.add_robot(RobotVisualConfig("bluey", base_position=(-0.4, 0, 0)))
        viewer.update(source.get_snapshot())
        if args.two_robots:
            erv_robot = SimulatedRobot(config)
            erv_publisher = SimulatedPublisher(erv_robot)
            erv_mapper = stack.enter_context(LegacyPyBulletIKMapper())
            erv_source = SimulatedRobotStateSource(
                "erv", erv_robot, erv_mapper
            )
            publishers["erv"] = erv_publisher
            sources["erv"] = erv_source
            viewer.add_robot(
                RobotVisualConfig(
                    "erv",
                    base_position=(0.4, 0, 0),
                    base_orientation_rpy=(0, 0, 3.14159),
                )
            )
            viewer.update(erv_source.get_snapshot())
        real_publishers: dict[str, Publisher] = {}
        for robot_id, host, port in args.real_robot:
            if robot_id not in publishers:
                raise ValueError(
                    f"real robot {robot_id!r} has no matching loaded visual robot"
                )
            real_publisher = Publisher(host, port)
            stack.callback(real_publisher.close)
            real_publishers[robot_id] = real_publisher
        recorder = TrajectoryRecorder(args.record) if args.record else None

        def consume(snapshot: RobotStateSnapshot) -> None:
            viewer.update(snapshot)
            viewer.step(1 / 60)
            if recorder:
                recorder.record(snapshot)

        try:
            if not args.no_demo:
                ScenarioRunner(publisher, source, timestep=1 / 60).run(
                    demo_scenario(), consume, realtime=not args.headless
                )
            if not args.headless and not args.exit_on_complete:
                controller = InteractiveSimulationController(
                    publishers,
                    sources,
                    viewer,
                    viewer.keyboard_flags(),
                    timestep=1 / 60,
                    real_publishers=real_publishers,
                )
                panel = (
                    None
                    if args.no_control_panel
                    else TkSimulationControlPanel(controller)
                )
                controller.run(panel)
        finally:
            if recorder:
                recorder.close()


def _run_replay(args: argparse.Namespace) -> None:
    trajectory = TrajectoryReplay.from_jsonl(args.replay)
    snapshots = tuple(trajectory)
    ids = tuple(dict.fromkeys(snapshot.robot_id for snapshot in snapshots))
    with PyBulletRobotViewer(gui=not args.headless) as viewer:
        if not args.headless:
            _print_camera_help()
        for index, robot_id in enumerate(ids):
            x_position = (index - (len(ids) - 1) / 2) * 0.8
            viewer.add_robot(
                RobotVisualConfig(robot_id, base_position=(x_position, 0, 0))
            )
        previous_time = snapshots[0].timestamp if snapshots else 0.0
        for snapshot in snapshots:
            delay = max(0.0, snapshot.timestamp - previous_time)
            if not args.headless and delay:
                time.sleep(delay / args.playback_speed)
            viewer.update(snapshot)
            viewer.step(delay or viewer.timestep)
            previous_time = snapshot.timestamp
        if not args.headless and not args.exit_on_complete:
            print("Replay complete. Close the PyBullet window or press Ctrl+C.")
            try:
                while viewer._p.isConnected(viewer.client_id):
                    viewer.step()
                    time.sleep(1 / 60)
            except KeyboardInterrupt:
                pass


def _print_camera_help() -> None:
    print(
        "Camera controls: hold Alt or Ctrl while dragging left mouse to orbit; "
        "hold Alt or Ctrl while dragging middle mouse to pan; use the wheel to zoom."
    )


def _parse_real_robot(value: str) -> tuple[str, str, int]:
    try:
        robot_id, endpoint = value.split("=", 1)
        host, port_text = endpoint.rsplit(":", 1)
        port = int(port_text)
    except (ValueError, TypeError) as error:
        raise argparse.ArgumentTypeError(
            "real robot must use ROBOT_ID=HOST:PORT"
        ) from error
    if not robot_id or not host or not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError(
            "real robot must contain an ID, host, and port from 1 to 65535"
        )
    return robot_id, host, port


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--headless", action="store_true", help="use DIRECT mode")
    parser.add_argument("--two-robots", action="store_true")
    parser.add_argument(
        "--no-demo",
        action="store_true",
        help="skip the scripted scenario and start interactive controls immediately",
    )
    parser.add_argument(
        "--no-control-panel",
        action="store_true",
        help="use keyboard controls without opening the Tk control window",
    )
    parser.add_argument(
        "--real-robot",
        action="append",
        default=[],
        type=_parse_real_robot,
        metavar="ROBOT_ID=HOST:PORT",
        help="register an explicitly configured real Publisher for UI selection",
    )
    parser.add_argument("--record", type=Path, help="record demo snapshots as JSONL")
    parser.add_argument("--replay", type=Path, help="replay a trajectory JSONL")
    parser.add_argument("--playback-speed", type=float, default=1.0)
    parser.add_argument("--exit-on-complete", action="store_true")
    args = parser.parse_args()
    if args.playback_speed <= 0:
        parser.error("--playback-speed must be positive")
    if args.replay:
        _run_replay(args)
    else:
        _run_demo(args)


if __name__ == "__main__":
    main()
