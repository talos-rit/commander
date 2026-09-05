"""Data contracts shared by capture, detection, recording, and replay."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

type BBox = tuple[int | float, int | float, int | float, int | float]


@dataclass(frozen=True, slots=True, eq=False)
class FramePacket:
    """One image acquired from one camera at a specific source time."""

    camera_id: str
    frame_sequence: int
    capture_timestamp: float
    image: np.ndarray = field(repr=False)

    def __post_init__(self) -> None:
        if self.frame_sequence < 0:
            raise ValueError("frame sequence must be non-negative")
        if not math.isfinite(self.capture_timestamp):
            raise ValueError("capture timestamp must be finite")
        if self.image.ndim < 2:
            raise ValueError("frame image must have at least two dimensions")
        self.image.setflags(write=False)


@dataclass(frozen=True, slots=True)
class LocalDetection:
    """Model output before it is associated with a source camera frame."""

    bounding_box: BBox
    confidence: float | None = None
    local_track_id: int | None = None


@dataclass(frozen=True, slots=True)
class PersonObservation:
    """A person detection tied to the exact source frame that produced it."""

    camera_id: str
    frame_sequence: int
    capture_timestamp: float
    bounding_box: BBox
    detection_confidence: float | None
    local_track_id: int | None

    def __post_init__(self) -> None:
        if self.frame_sequence < 0:
            raise ValueError("frame sequence must be non-negative")
        if not math.isfinite(self.capture_timestamp):
            raise ValueError("capture timestamp must be finite")
        if self.detection_confidence is not None and not (
            0.0 <= self.detection_confidence <= 1.0
        ):
            raise ValueError("detection confidence must be between zero and one")


@dataclass(frozen=True, slots=True)
class ObservationFrame:
    """All person observations for one source frame, including empty frames."""

    camera_id: str
    frame_sequence: int
    capture_timestamp: float
    observations: tuple[PersonObservation, ...] = ()

    def __post_init__(self) -> None:
        for observation in self.observations:
            if (
                observation.camera_id != self.camera_id
                or observation.frame_sequence != self.frame_sequence
                or observation.capture_timestamp != self.capture_timestamp
            ):
                raise ValueError("observation metadata does not match its frame")
