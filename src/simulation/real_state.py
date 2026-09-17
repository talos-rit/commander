"""Measured ER-V state adapters and a deterministic offline telemetry fake.

The real viewer must never turn a connection, command ACK, or viewer startup into
an assumed home pose.  Only a telemetry frame received in the current connection
epoch can produce a measured snapshot.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Protocol

from src.robot_state import MappingQuality, RobotStateSnapshot, StateSourceType

from .erv_calibration import BASE_CALIBRATION, map_arm_controller_coordinates


class TelemetryHealth(str, Enum):
    DISCONNECTED = "disconnected"
    WAITING = "waiting"
    LIVE = "live"
    STALE = "stale"


@dataclass(frozen=True)
class TelemetryHealthSnapshot:
    connected: bool
    has_state: bool
    last_receive_monotonic: float | None
    age_seconds: float | None
    estimated_rate_hz: float | None
    health: TelemetryHealth


class ERVTelemetryPublisher(Protocol):
    def is_connected(self) -> bool: ...
    def get_erv_encoder_counts(self) -> tuple[int, ...] | None: ...
    def get_erv_joint_counts(self) -> tuple[int, ...] | None: ...
    def get_erv_telemetry_received_monotonic(self) -> float | None: ...


class MeasuredERVStateSource:
    """Convert current-epoch ER-V telemetry into viewer snapshots.

    Absolute controller coordinates are mapped through explicit affine reference
    calibrations; importantly, no first-frame reference is captured.  Roll and
    gripper remain absent because their telemetry calibration is not established.
    """

    def __init__(
        self, robot_id: str, publisher: ERVTelemetryPublisher, *,
        stale_after_seconds: float = 1.5, clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if stale_after_seconds <= 0:
            raise ValueError("stale_after_seconds must be positive")
        self._robot_id, self._publisher = robot_id, publisher
        self._stale_after, self._clock = stale_after_seconds, clock
        self._was_connected = False
        self._minimum_fresh_timestamp = float("-inf")
        self._accepted_timestamp: float | None = None
        self._intervals: list[float] = []

    @property
    def robot_id(self) -> str:
        return self._robot_id

    def telemetry_health(self) -> TelemetryHealthSnapshot:
        now = self._clock()
        connected = self._publisher.is_connected()
        if not connected:
            self._was_connected = False
            # A frame cached at exactly the disconnect observation time still
            # belongs to the old epoch.  The next epoch must be strictly newer.
            self._minimum_fresh_timestamp = math.nextafter(now, math.inf)
            self._accepted_timestamp = None
            self._intervals.clear()
            return TelemetryHealthSnapshot(False, False, None, None, None, TelemetryHealth.DISCONNECTED)
        if not self._was_connected:
            # A reconnect invalidates any cached Publisher telemetry.  Accept only
            # frames that arrive after this connection epoch begins.
            self._was_connected = True
            if self._minimum_fresh_timestamp == float("-inf"):
                self._minimum_fresh_timestamp = now
            self._accepted_timestamp = None
            self._intervals.clear()
        received = self._publisher.get_erv_telemetry_received_monotonic()
        if received is not None and received >= self._minimum_fresh_timestamp:
            if self._accepted_timestamp is not None and received > self._accepted_timestamp:
                self._intervals.append(received - self._accepted_timestamp)
                self._intervals = self._intervals[-8:]
            self._accepted_timestamp = received
        if self._accepted_timestamp is None:
            return TelemetryHealthSnapshot(True, False, None, None, None, TelemetryHealth.WAITING)
        age = max(0.0, now - self._accepted_timestamp)
        rate = (len(self._intervals) / sum(self._intervals)) if self._intervals and sum(self._intervals) else None
        health = TelemetryHealth.LIVE if age <= self._stale_after else TelemetryHealth.STALE
        return TelemetryHealthSnapshot(True, True, self._accepted_timestamp, age, rate, health)

    def get_snapshot(self) -> RobotStateSnapshot:
        health = self.telemetry_health()
        joint_counts = self._publisher.get_erv_joint_counts()
        if not health.has_state or joint_counts is None:
            return RobotStateSnapshot(
                robot_id=self._robot_id, timestamp=self._clock(), source_type=StateSourceType.REAL,
                movement_state="unknown", joint_mapping_quality=MappingQuality.UNKNOWN,
            )
        positions: dict[str, float] = {}
        if joint_counts is not None and len(joint_counts) == 5:
            base, shoulder, elbow, pitch, _roll = joint_counts
            positions[BASE_CALIBRATION.joint_name] = BASE_CALIBRATION.to_urdf(base)
        elif len(joint_counts) == 4:
            shoulder, elbow, pitch, _roll = joint_counts
        else:
            return RobotStateSnapshot(robot_id=self._robot_id, timestamp=self._clock(), source_type=StateSourceType.REAL, movement_state="unknown")
        positions.update(map_arm_controller_coordinates(shoulder, elbow, pitch))
        return RobotStateSnapshot(
            robot_id=self._robot_id, timestamp=health.last_receive_monotonic or self._clock(),
            source_type=StateSourceType.REAL, movement_state="unknown",
            joint_positions=positions,
            joint_mapping_quality=MappingQuality.PARTIALLY_CALIBRATED,
        )


class FakeERVTelemetryPublisher:
    """Deterministic, transport-free stand-in for the real Publisher."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock, self._connected = clock, False
        self._encoder_counts: tuple[int, ...] | None = None
        self._joint_counts: tuple[int, ...] | None = None
        self._received: float | None = None

    def connect(self) -> None: self._connected = True
    def disconnect(self) -> None: self._connected = False
    def is_connected(self) -> bool: return self._connected
    def get_erv_encoder_counts(self) -> tuple[int, ...] | None: return self._encoder_counts
    def get_erv_joint_counts(self) -> tuple[int, ...] | None: return self._joint_counts
    def get_erv_telemetry_received_monotonic(self) -> float | None: return self._received

    def emit(self, encoder_counts: tuple[int, ...], joint_counts: tuple[int, ...] | None = None) -> None:
        if not self._connected:
            raise RuntimeError("cannot emit telemetry while disconnected")
        if len(encoder_counts) < 4:
            raise ValueError("ER-V telemetry requires at least four encoder counts")
        self._encoder_counts, self._joint_counts = tuple(encoder_counts), joint_counts
        self._received = self._clock()
