"""Conversion of YOLO tensor outputs into Commander's model-neutral contract."""

from __future__ import annotations

import numpy as np

from src.observations.types import LocalDetection


def local_detections_from_arrays(
    xyxy,
    confidences,
    track_ids=None,
) -> list[LocalDetection]:
    """Keep each bounding box associated with its confidence and local track ID."""

    boxes = np.asarray(xyxy).astype(int)
    confidence_values = np.asarray(confidences).flatten()
    id_values = np.asarray(track_ids).flatten() if track_ids is not None else None
    order = np.argsort(id_values) if id_values is not None else range(len(boxes))
    return [
        LocalDetection(
            bounding_box=tuple(boxes[index].tolist()),
            confidence=float(confidence_values[index]),
            local_track_id=int(id_values[index]) if id_values is not None else None,
        )
        for index in order
    ]
