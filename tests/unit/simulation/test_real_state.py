import math

import pytest

from src.simulation.real_state import (
    FakeERVTelemetryPublisher,
    MeasuredERVStateSource,
    TelemetryHealth,
    _SHOULDER_VERTICAL_OFFSET,
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
    assert source.get_snapshot().movement_state == "unknown"
    publisher.disconnect()
    assert source.get_snapshot().movement_state == "unknown"

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
    assert snapshot.joint_positions["shoulder_joint"] == pytest.approx(_SHOULDER_VERTICAL_OFFSET + 100 * math.pi / (180 * 33.2121))


def test_base_inclusive_controller_coordinates_do_not_require_raw_encoder_stream():
    clock = Clock()
    publisher = FakeERVTelemetryPublisher(clock=clock)
    publisher.connect()
    source = MeasuredERVStateSource("bingo", publisher, clock=clock)
    clock.advance(0.1)
    publisher.emit((1, 2, 3, 4), (50, 100, 200, 300, 400))
    snapshot = source.get_snapshot()
    assert snapshot.joint_positions["base_joint"] == pytest.approx(50 * math.pi / (180 * 42.5666))


def test_physical_vertical_reference_maps_shoulder_and_elbow_straight():
    clock = Clock()
    publisher = FakeERVTelemetryPublisher(clock=clock)
    publisher.connect()
    source = MeasuredERVStateSource("bingo", publisher, clock=clock)
    clock.advance(0.1)
    # Bingo observed physically ramrod straight up at these controller counts.
    publisher.emit((1, 2, 3, 4), (516, 1088, 2113, 1151, -1432))

    positions = source.get_snapshot().joint_positions
    assert positions["shoulder_joint"] == pytest.approx(-math.pi / 2)
    assert positions["elbow_joint"] == pytest.approx(0.0)


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
