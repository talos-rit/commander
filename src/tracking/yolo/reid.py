"""Body embeddings from a YOLO classifier, the encoder BoT-SORT uses for ReID."""

from collections.abc import Sequence
from os import path

import numpy as np
from ultralytics.trackers.bot_sort import ReID

from assets import join_paths
from src.observations.types import BBox

REID_WEIGHTS = "yolo26n-cls.pt"
"""Downloaded into assets/yolo on first use."""


class YoloReIDEmbedder:
    def __init__(self, weights: str = path.join(join_paths("yolo"), REID_WEIGHTS)):
        self._reid = ReID(weights)

    def embed(self, image: np.ndarray, boxes: Sequence[BBox]) -> list[np.ndarray]:
        if not boxes:
            return []
        x1, y1, x2, y2 = np.asarray(boxes, dtype=np.float64).T
        xywh = np.column_stack(((x1 + x2) / 2, (y1 + y2) / 2, x2 - x1, y2 - y1))
        return [np.asarray(f, dtype=np.float32).ravel() for f in self._reid(image, xywh)]
