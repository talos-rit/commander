import math

import pytest

from src.simulation.real_state import (
    FakeERVTelemetryPublisher,
    MeasuredERVStateSource,
    TelemetryHealth,
)
from src.simulation.erv_calibration import (
    BASE_CALIBRATION,
    ELBOW_CALIBRATION,
    PITCH_CALIBRATION,
    SHOULDER_CALIBRATION,
    VERTICAL_STRAIGHT_URDF,
    CalibrationEvidence,
    JointCalibration,
    map_arm_controller_coordinates,
)
from src.robot_state import MappingQuality, StateSourceType


class Clock:
    def __init__(self): self.value = 0.0
    def __call__(self): return self.value
    def advance(self, seconds): self.value += seconds


def test_real_source_lifecycle_reconnect_and_staleness():
    clock = Clock()
    publisher = FakeERVTelemetryPublisher(clock=clock)
    source = MeasuredERVStateSource("bingo", publisher, stale_after_seconds=1.0, clock=clock)

    assert source.telemetry_health().health is TelemetryHealth.DISCONNECTED
    publisher.connect()
    assert source.get_snapshot().movement_state == "unknown"
    assert source.get_snapshot().joint_positions is None

    clock.advance(0.1)
    publisher.emit((43, 16484, -16184, 10))
    live = source.get_snapshot()
    assert source.telemetry_health().health is TelemetryHealth.LIVE
    assert live.source_type is StateSourceType.REAL
    assert live.joint_mapping_quality is MappingQuality.UNKNOWN
    assert live.joint_positions is None

    clock.advance(1.1)
    assert source.telemetry_health().health is TelemetryHealth.STALE
    assert source.get_snapshot().movement_state == "unknown"
    publisher.disconnect()
    disconnected = source.get_snapshot()
    assert disconnected.movement_state == "unknown"
    assert disconnected.joint_positions is None

    publisher.connect()
    # Cached pre-disconnect counts are deliberately not authoritative.
    assert source.get_snapshot().movement_state == "unknown"
    clock.advance(0.1)
    publisher.emit((44, 16485, -16185, 11))
    assert source.get_snapshot().movement_state == "unknown"


def test_rate_uses_monotonic_receive_intervals_and_joint_telemetry_wins():
    clock = Clock()
    publisher = FakeERVTelemetryPublisher(clock=clock)
    publisher.connect()
    source = MeasuredERVStateSource("bingo", publisher, clock=clock)
    clock.advance(0.1)
    publisher.emit((1, 2, 3, 4))
    source.get_snapshot()
    clock.advance(0.5)
    publisher.emit((1, 2, 3, 4), (100, 200, 300, 400))
    snapshot = source.get_snapshot()
    assert source.telemetry_health().estimated_rate_hz == pytest.approx(2.0)
    assert snapshot.joint_positions["shoulder_joint"] == pytest.approx(
        SHOULDER_CALIBRATION.to_urdf(100)
    )
    assert snapshot.joint_mapping_quality is MappingQuality.PARTIALLY_CALIBRATED


def test_base_inclusive_controller_coordinates_do_not_require_raw_encoder_stream():
    clock = Clock()
    publisher = FakeERVTelemetryPublisher(clock=clock)
    publisher.connect()
    source = MeasuredERVStateSource("bingo", publisher, clock=clock)
    clock.advance(0.1)
    publisher.emit((1, 2, 3, 4), (50, 100, 200, 300, 400))
    snapshot = source.get_snapshot()
    assert snapshot.joint_positions["base_joint"] == pytest.approx(
        BASE_CALIBRATION.to_urdf(50)
    )
    assert BASE_CALIBRATION.reference_evidence is CalibrationEvidence.UNVERIFIED


def test_physical_vertical_reference_maps_complete_observed_pose():
    clock = Clock()
    publisher = FakeERVTelemetryPublisher(clock=clock)
    publisher.connect()
    source = MeasuredERVStateSource("bingo", publisher, clock=clock)
    clock.advance(0.1)
    # Bingo observed physically ramrod straight up at these controller counts.
    publisher.emit((1, 2, 3, 4), (516, 1088, 2113, 1151, -1432))

    positions = source.get_snapshot().joint_positions
    assert positions["shoulder_joint"] == pytest.approx(
        VERTICAL_STRAIGHT_URDF["shoulder_joint"]
    )
    assert positions["elbow_joint"] == pytest.approx(
        VERTICAL_STRAIGHT_URDF["elbow_joint"]
    )
    assert positions["pitch_joint"] == pytest.approx(
        VERTICAL_STRAIGHT_URDF["pitch_joint"]
    )


def test_calibration_directions_around_vertical_reference():
    assert ELBOW_CALIBRATION.to_urdf(2113) == pytest.approx(0.0)
    assert ELBOW_CALIBRATION.to_urdf(2112) > ELBOW_CALIBRATION.to_urdf(2113)
    assert ELBOW_CALIBRATION.to_urdf(2114) < ELBOW_CALIBRATION.to_urdf(2113)

    shoulder_reference = SHOULDER_CALIBRATION.to_urdf(1088)
    assert shoulder_reference == pytest.approx(-math.pi / 2)
    assert SHOULDER_CALIBRATION.to_urdf(1087) < shoulder_reference
    assert SHOULDER_CALIBRATION.to_urdf(1089) > shoulder_reference

    assert PITCH_CALIBRATION.to_urdf(1151) == pytest.approx(0.0)


def test_shoulder_motion_keeps_independent_forearm_orientation_vertical():
    reference = map_arm_controller_coordinates(1088, 2113, 1151)
    shoulder_moved = map_arm_controller_coordinates(444, 2113, 1151)

    assert shoulder_moved["shoulder_joint"] < reference["shoulder_joint"]
    assert shoulder_moved["elbow_joint"] > reference["elbow_joint"]
    assert (
        shoulder_moved["shoulder_joint"] + shoulder_moved["elbow_joint"]
    ) == pytest.approx(-math.pi / 2)


def test_reconnect_reconstructs_same_absolute_pose_without_first_frame_zeroing():
    clock = Clock()
    publisher = FakeERVTelemetryPublisher(clock=clock)
    source = MeasuredERVStateSource("bingo", publisher, clock=clock)
    away_from_reference = (700, 900, 1800, 1000, -1200)

    publisher.connect()
    clock.advance(0.1)
    publisher.emit((1, 2, 3, 4), away_from_reference)
    before = source.get_snapshot().joint_positions

    publisher.disconnect()
    assert source.get_snapshot().joint_positions is None
    publisher.connect()
    assert source.get_snapshot().joint_positions is None
    clock.advance(0.1)
    publisher.emit((5, 6, 7, 8), away_from_reference)
    after = source.get_snapshot().joint_positions

    assert after == before


def test_joint_calibration_validates_affine_parameters():
    common = dict(
        joint_name="joint",
        controller_reference=0,
        urdf_reference=0.0,
        reference_evidence=CalibrationEvidence.UNVERIFIED,
        direction_evidence=CalibrationEvidence.UNVERIFIED,
        scale_evidence=CalibrationEvidence.UNVERIFIED,
        note="test",
    )
    with pytest.raises(ValueError, match="counts_per_degree"):
        JointCalibration(counts_per_degree=0.0, direction=1, **common)
    with pytest.raises(ValueError, match="direction"):
        JointCalibration(counts_per_degree=1.0, direction=0, **common)


def test_legacy_joint_frame_keeps_base_unknown_even_when_raw_encoders_exist():
    clock = Clock()
    publisher = FakeERVTelemetryPublisher(clock=clock)
    publisher.connect()
    source = MeasuredERVStateSource("bingo", publisher, clock=clock)
    clock.advance(0.1)
    publisher.emit((999, 1, 2, 3), (10, 20, 30, 40))
    snapshot = source.get_snapshot()
    assert "base_joint" not in snapshot.joint_positions


def test_fake_requires_live_connection_and_real_source_rejects_bad_threshold():
    fake = FakeERVTelemetryPublisher()
    with pytest.raises(RuntimeError):
        fake.emit((1, 2, 3, 4))
    with pytest.raises(ValueError):
        MeasuredERVStateSource("bingo", fake, stale_after_seconds=0)
