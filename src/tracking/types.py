from src.observations.types import BBox, LocalDetection, PersonObservation

type Frame = tuple[int, int]  # (height, width)
type BBoxMapping = dict[str, list[BBox]]
type ObservationMapping = dict[str, list[PersonObservation]]

__all__ = [
    "BBox",
    "BBoxMapping",
    "Frame",
    "LocalDetection",
    "ObservationMapping",
    "PersonObservation",
]
