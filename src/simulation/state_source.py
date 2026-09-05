"""Adapters from simulation state into the common robot snapshot contract."""

from __future__ import annotations

import math
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Protocol

from src.robot_state import (
    CommandSnapshot,
    FaultSnapshot,
    LogicalPose,
    MappingQuality,
    RobotStateSnapshot,
    StateSourceType,
)

from .robot import RobotPose, RobotState, SimulatedRobot


LEGACY_URDF_PATH = (
    Path(__file__).resolve().parents[2]
    / "digital_twin"
    / "sboter4u_model"
    / "robots"
    / "sboter4u_model.URDF"
)


class LogicalJointMapper(Protocol):
    quality: MappingQuality

    def map_positions(self, pose: LogicalPose) -> Mapping[str, float]: ...

    def map_velocities(self, velocity: LogicalPose) -> Mapping[str, float]: ...


@dataclass(frozen=True)
class JointAxisCalibration:
    """Explicit linear visualization calibration for one logical axis."""

    logical_axis: str
    joint_name: str
    radians_per_unit: float
    offset_radians: float = 0.0


@dataclass(frozen=True)
class ConfigurableJointMapper:
    """Maps only declared axes; it never infers missing kinematics."""

    calibrations: tuple[JointAxisCalibration, ...]
    fixed_positions: Mapping[str, float]
    quality: MappingQuality

    def map_positions(self, pose: LogicalPose) -> Mapping[str, float]:
        positions = dict(self.fixed_positions)
        for item in self.calibrations:
            positions[item.joint_name] = (
                getattr(pose, item.logical_axis) * item.radians_per_unit
                + item.offset_radians
            )
        return positions

    def map_velocities(self, velocity: LogicalPose) -> Mapping[str, float]:
        return {
            item.joint_name: getattr(velocity, item.logical_axis)
            * item.radians_per_unit
            for item in self.calibrations
        }


def legacy_visual_mapping() -> ConfigurableJointMapper:
    """Return the old twin's useful but *unvalidated* visual approximation.

    The old twin mapped azimuth to ``base_joint`` and altitude to ``pitch_joint``
    while treating command values as degrees. The remaining values are its home
    posture. This function is opt-in and labels every result as an approximation.
    """

    return ConfigurableJointMapper(
        calibrations=(
            JointAxisCalibration("azimuth", "base_joint", math.pi / 180.0, 0.0),
            JointAxisCalibration(
                "altitude", "pitch_joint", math.pi / 180.0, 0.41547
            ),
        ),
        fixed_positions={
            "shoulder_joint": -2.09925,
            "elbow_joint": 1.65843,
            "roll_joint": 0.0,
            "pad1_joint": 0.0,
            "pad2_joint": 0.0,
        },
        quality=MappingQuality.LEGACY_APPROXIMATION,
    )


class LegacyPyBulletIKMapper:
    """Opt-in legacy Cartesian visualization using a private DIRECT IK client.

    Cartesian tenths-of-a-millimetre values are applied as offsets in URDF world
    X/Y/Z. That axis alignment is not physically calibrated, so output remains a
    ``LEGACY_APPROXIMATION``. PyBullet is a kinematic solver here, not the plant.
    """

    quality = MappingQuality.LEGACY_APPROXIMATION

    def __init__(self, urdf_path: Path = LEGACY_URDF_PATH) -> None:
        try:
            import pybullet  # type: ignore[import-not-found]
        except ImportError as error:  # pragma: no cover - installation concern
            raise RuntimeError(
                "PyBullet is required for the legacy IK mapper"
            ) from error
        self._p = pybullet
        self._client_id = pybullet.connect(pybullet.DIRECT)
        self._temporary_directory: tempfile.TemporaryDirectory | None = None
        resolved = self._resolve_urdf(urdf_path)
        self._body_id = pybullet.loadURDF(
            str(resolved), useFixedBase=True, physicsClientId=self._client_id
        )
        self._joint_indices: dict[str, int] = {}
        self._joint_limits: dict[str, tuple[float, float]] = {}
        for index in range(
            pybullet.getNumJoints(self._body_id, physicsClientId=self._client_id)
        ):
            info = pybullet.getJointInfo(
                self._body_id, index, physicsClientId=self._client_id
            )
            name = info[1].decode("utf-8")
            self._joint_indices[name] = index
            self._joint_limits[name] = (float(info[8]), float(info[9]))
        self._joint_names = tuple(
            name
            for name, _index in sorted(
                self._joint_indices.items(), key=lambda item: item[1]
            )
        )
        legacy_home = dict(legacy_visual_mapping().map_positions(LogicalPose()))
        self._rest_positions = tuple(legacy_home[name] for name in self._joint_names)
        for name, position in zip(self._joint_names, self._rest_positions):
            pybullet.resetJointState(
                self._body_id,
                self._joint_indices[name],
                position,
                physicsClientId=self._client_id,
            )
        self._end_effector_index = self._joint_indices["roll_joint"]
        self._home_endpoint = pybullet.getLinkState(
            self._body_id,
            self._end_effector_index,
            physicsClientId=self._client_id,
        )[4]

    def map_positions(self, pose: LogicalPose) -> Mapping[str, float]:
        target = tuple(
            self._home_endpoint[index]
            + getattr(pose, ("x", "y", "z")[index]) * 0.0001
            for index in range(3)
        )
        lower = [self._joint_limits[name][0] for name in self._joint_names]
        upper = [self._joint_limits[name][1] for name in self._joint_names]
        solution = self._p.calculateInverseKinematics(
            self._body_id,
            self._end_effector_index,
            target,
            lowerLimits=lower,
            upperLimits=upper,
            jointRanges=[high - low for low, high in zip(lower, upper)],
            restPoses=self._rest_positions,
            maxNumIterations=100,
            residualThreshold=1e-6,
            physicsClientId=self._client_id,
        )
        positions = {
            name: min(max(float(value), lower[index]), upper[index])
            for index, (name, value) in enumerate(zip(self._joint_names, solution))
        }
        positions["base_joint"] += pose.azimuth * math.pi / 180.0
        positions["pitch_joint"] += pose.altitude * math.pi / 180.0
        for name in ("base_joint", "pitch_joint"):
            low, high = self._joint_limits[name]
            positions[name] = min(max(positions[name], low), high)
        return positions

    def map_velocities(self, velocity: LogicalPose) -> Mapping[str, float]:
        # Nonlinear Cartesian joint velocities require a Jacobian; do not invent one.
        return {
            "base_joint": velocity.azimuth * math.pi / 180.0,
            "pitch_joint": velocity.altitude * math.pi / 180.0,
        }

    def close(self) -> None:
        if self._client_id >= 0 and self._p.isConnected(self._client_id):
            self._p.disconnect(physicsClientId=self._client_id)
        self._client_id = -1
        if self._temporary_directory is not None:
            self._temporary_directory.cleanup()
            self._temporary_directory = None

    def __enter__(self) -> LegacyPyBulletIKMapper:
        return self

    def __exit__(self, *_args) -> None:
        self.close()

    def _resolve_urdf(self, source: Path) -> Path:
        source = source.resolve()
        text = source.read_text(encoding="utf-8")
        marker = "package://sboter4u_model/"
        if marker not in text:
            return source
        package_root = source.parent.parent.resolve().as_posix() + "/"
        self._temporary_directory = tempfile.TemporaryDirectory(
            prefix="commander-ik-urdf-"
        )
        resolved = Path(self._temporary_directory.name) / source.name
        resolved.write_text(text.replace(marker, package_root), encoding="utf-8")
        return resolved


class SimulatedRobotStateSource:
    """Read-only state adapter; commands still flow through a Publisher."""

    def __init__(
        self,
        robot_id: str,
        robot: SimulatedRobot,
        joint_mapper: LogicalJointMapper | None = None,
    ) -> None:
        self._robot_id = robot_id
        self._robot = robot
        self._joint_mapper = joint_mapper

    @property
    def robot_id(self) -> str:
        return self._robot_id

    def get_snapshot(self) -> RobotStateSnapshot:
        return snapshot_from_simulated_state(
            self._robot_id, self._robot.get_state(), self._joint_mapper
        )


def snapshot_from_simulated_state(
    robot_id: str,
    state: RobotState,
    joint_mapper: LogicalJointMapper | None = None,
) -> RobotStateSnapshot:
    command = state.current_command
    fault = state.fault
    logical_pose = LogicalPose(**vars(state.pose))
    logical_velocity = LogicalPose(**vars(state.velocity))
    return RobotStateSnapshot(
        robot_id=robot_id,
        timestamp=state.timestamps.updated_at,
        source_type=StateSourceType.SIMULATED,
        movement_state=state.movement_state.value,
        logical_pose=logical_pose,
        logical_velocity=logical_velocity,
        joint_positions=(
            dict(joint_mapper.map_positions(logical_pose)) if joint_mapper else None
        ),
        joint_velocities=(
            dict(joint_mapper.map_velocities(logical_velocity))
            if joint_mapper
            else None
        ),
        joint_mapping_quality=(
            joint_mapper.quality if joint_mapper else MappingQuality.UNKNOWN
        ),
        homed=state.homed,
        current_command=(
            CommandSnapshot(
                command_id=command.command_id,
                kind=command.kind.value,
                status=command.status.value,
                issued_at=command.issued_at,
                starts_at=command.starts_at,
                target=(
                    LogicalPose(**vars(command.target)) if command.target else None
                ),
                direction=(
                    LogicalPose(**vars(command.direction))
                    if command.direction
                    else None
                ),
            )
            if command
            else None
        ),
        fault=(
            FaultSnapshot(fault.code, fault.message, fault.timestamp) if fault else None
        ),
    )
