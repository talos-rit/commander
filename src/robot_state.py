"""Transport-neutral robot state consumed by visualization and recording tools."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Mapping, Protocol


class StateSourceType(str, Enum):
    SIMULATED = "simulated"
    REAL = "real"
    REPLAY = "replay"
    COMMAND_ESTIMATE = "command_estimate"


class MappingQuality(str, Enum):
    """How confidently logical coordinates were converted to physical joints."""

    PHYSICALLY_VALIDATED = "physically_validated"
    LEGACY_APPROXIMATION = "legacy_approximation"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class LogicalPose:
    """Commander's logical pose; this is not inherently a physical joint pose."""

    azimuth: float = 0.0
    altitude: float = 0.0
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


@dataclass(frozen=True)
class CommandSnapshot:
    command_id: int | str
    kind: str
    status: str
    issued_at: float
    starts_at: float | None = None
    target: LogicalPose | None = None
    direction: LogicalPose | None = None


@dataclass(frozen=True)
class FaultSnapshot:
    code: str
    message: str
    timestamp: float


@dataclass(frozen=True)
class RobotStateSnapshot:
    """State contract shared by simulated, replayed, and future real robots.

    Optional values remain ``None`` when the source cannot observe them. In
    particular, a logical pose is never treated as joint telemetry unless a named,
    explicitly qualified mapping supplied ``joint_positions``.
    """

    robot_id: str
    timestamp: float
    source_type: StateSourceType
    movement_state: str | None = None
    logical_pose: LogicalPose | None = None
    logical_velocity: LogicalPose | None = None
    joint_positions: Mapping[str, float] | None = None
    joint_velocities: Mapping[str, float] | None = None
    joint_mapping_quality: MappingQuality = MappingQuality.UNKNOWN
    homed: bool | None = None
    current_command: CommandSnapshot | None = None
    fault: FaultSnapshot | None = None


class RobotStateSource(Protocol):
    """Narrow seam a live simulator or telemetry adapter must implement."""

    @property
    def robot_id(self) -> str: ...

    def get_snapshot(self) -> RobotStateSnapshot: ...


def snapshot_to_dict(snapshot: RobotStateSnapshot) -> dict:
    """Return a JSON-safe representation without mutating the snapshot."""

    value = asdict(snapshot)
    value["source_type"] = snapshot.source_type.value
    value["joint_mapping_quality"] = snapshot.joint_mapping_quality.value
    return value


def snapshot_from_dict(value: dict) -> RobotStateSnapshot:
    """Construct a snapshot from the version-independent JSON representation."""

    logical_pose = value.get("logical_pose")
    logical_velocity = value.get("logical_velocity")
    command = value.get("current_command")
    fault = value.get("fault")
    if command:
        command = dict(command)
        if command.get("target") is not None:
            command["target"] = LogicalPose(**command["target"])
        if command.get("direction") is not None:
            command["direction"] = LogicalPose(**command["direction"])
        command = CommandSnapshot(**command)
    return RobotStateSnapshot(
        robot_id=value["robot_id"],
        timestamp=float(value["timestamp"]),
        source_type=StateSourceType(value["source_type"]),
        movement_state=value.get("movement_state"),
        logical_pose=LogicalPose(**logical_pose) if logical_pose is not None else None,
        logical_velocity=(
            LogicalPose(**logical_velocity) if logical_velocity is not None else None
        ),
        joint_positions=value.get("joint_positions"),
        joint_velocities=value.get("joint_velocities"),
        joint_mapping_quality=MappingQuality(
            value.get("joint_mapping_quality", MappingQuality.UNKNOWN.value)
        ),
        homed=value.get("homed"),
        current_command=command,
        fault=FaultSnapshot(**fault) if fault is not None else None,
    )
