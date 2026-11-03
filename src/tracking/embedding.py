"""Appearance embeddings: a vector per person crop, close for the same person."""

import threading
from collections.abc import Callable, Sequence
from importlib.util import find_spec
from typing import Protocol

import numpy as np
from loguru import logger

from src.observations.types import BBox


class Embedder(Protocol):
    def embed(self, image: np.ndarray, boxes: Sequence[BBox]) -> list[np.ndarray]:
        """One vector per box, in order, or an empty list if it cannot embed yet."""
        ...


class FaceEmbedder(Protocol):
    def embed(self, image: np.ndarray, boxes: Sequence[BBox]) -> list[np.ndarray | None]:
        """One face vector per person box, None where no clear face shows, or an
        empty list if it cannot embed yet."""
        ...


class BackgroundEmbedder:
    """Loads an embedder on a background thread so startup never waits on it.

    Embeds nothing until the model is ready, or ever if loading fails.
    """

    def __init__(self, load: Callable[[], Embedder | FaceEmbedder], name: str = "embedder"):
        self._embedder: Embedder | FaceEmbedder | None = None
        self._failed = False
        self._thread = threading.Thread(
            target=self._load, args=(load, name), name=f"load-{name}", daemon=True
        )
        self._thread.start()

    def _load(self, load: Callable[[], Embedder | FaceEmbedder], name: str) -> None:
        try:
            self._embedder = load()
            logger.info("Loaded {} for re-identification", name)
        except Exception as exc:
            self._failed = True
            logger.warning("Could not load {}; recognizing people without it: {}", name, exc)

    @property
    def ready(self) -> bool:
        return self._embedder is not None

    def embed(self, image: np.ndarray, boxes: Sequence[BBox]) -> list:
        if self._embedder is None or not boxes:
            return []
        return self._embedder.embed(image, boxes)


def _load_yolo_reid() -> Embedder:
    from src.tracking.yolo.reid import YoloReIDEmbedder

    return YoloReIDEmbedder()


def default_embedder() -> Embedder | None:
    """The body embedder, or None when the yolo extra is not installed."""
    if find_spec("ultralytics") is None:
        logger.info("Install the yolo extra to also recognize people by their clothes")
        return None
    return BackgroundEmbedder(_load_yolo_reid, "YOLO ReID")


def _load_sface() -> FaceEmbedder:
    from src.tracking.face import SFaceEmbedder

    return SFaceEmbedder()


def default_face_embedder() -> FaceEmbedder:
    """The face embedder. Its models download on first use."""
    return BackgroundEmbedder(_load_sface, "face recognizer")
