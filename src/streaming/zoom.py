"""Digital zoom: crop each frame around one tracked subject and scale it back up."""

import math
import threading
import time
from collections.abc import Callable, Iterable

import cv2
import numpy as np

from src.observations.types import BBox, PersonObservation

type Rect = tuple[float, float, float, float]  # x1, y1, x2, y2

DEFAULT_FILL = 0.6
"""Share of the crop the subject's box should take up, by height or width."""
MIN_FILL = 0.2
MAX_FILL = 0.9
MAX_ZOOM = 4.0
"""Never crop below 1/MAX_ZOOM of the frame; upscaling past this is too blurry."""
SMOOTHING_S = 0.3
"""Time constant for easing the crop toward its target. Larger is calmer."""
LOST_HOLD_S = 1.0
"""How long to hold the last framing after the subject drops out of detection."""


def framing_rect(
    bbox: BBox, frame_width: int, frame_height: int, fill: float, max_zoom: float = MAX_ZOOM
) -> Rect:
    """The crop, in the frame's aspect ratio, that frames `bbox` at `fill`.

    The crop is always at least as large as the box, so shifting it to stay
    inside the frame never cuts the subject off.
    """
    x1, y1, x2, y2 = bbox
    box_width = max(1.0, float(x2 - x1))
    box_height = max(1.0, float(y2 - y1))
    aspect = frame_width / frame_height
    width = max(box_width / fill, box_height / fill * aspect)
    width = min(max(width, frame_width / max_zoom), frame_width)
    height = width / aspect
    left = min(max((x1 + x2) / 2 - width / 2, 0.0), frame_width - width)
    top = min(max((y1 + y2) / 2 - height / 2, 0.0), frame_height - height)
    return (left, top, left + width, top + height)


def _lerp(a: Rect, b: Rect, t: float) -> Rect:
    return (
        a[0] + (b[0] - a[0]) * t,
        a[1] + (b[1] - a[1]) * t,
        a[2] + (b[2] - a[2]) * t,
        a[3] + (b[3] - a[3]) * t,
    )


class DigitalZoom:
    """Smoothed crop that follows one subject, chosen by its tracker ID.

    With no target, or once the target has been missing longer than
    `lost_hold_s`, the crop eases back out to the full frame. Safe to call from
    several frame consumers at once (web feed, virtual camera).
    """

    def __init__(
        self,
        fill: float = DEFAULT_FILL,
        max_zoom: float = MAX_ZOOM,
        smoothing_s: float = SMOOTHING_S,
        lost_hold_s: float = LOST_HOLD_S,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.max_zoom = max_zoom
        self.smoothing_s = smoothing_s
        self.lost_hold_s = lost_hold_s
        self.clock = clock
        self._lock = threading.Lock()
        self._fill = DEFAULT_FILL
        self.set_fill(fill)
        self._rect: Rect | None = None
        self._frame_size: tuple[int, int] | None = None
        self._last_update: float | None = None
        self._target: int | None = None
        self._held: Rect | None = None
        self._last_seen: float | None = None
        self._locked = False

    @property
    def fill(self) -> float:
        return self._fill

    def set_fill(self, fill: float) -> float:
        if not MIN_FILL <= fill <= MAX_FILL:
            raise ValueError(f"Fill must be from {MIN_FILL} to {MAX_FILL}, got {fill}")
        self._fill = float(fill)
        return self._fill

    def update(
        self,
        frame_shape: tuple[int, ...],
        observations: Iterable[PersonObservation],
        target_id: int | None,
    ) -> Rect:
        """Advance the crop one step toward where `target_id` should be framed."""
        height, width = frame_shape[:2]
        full: Rect = (0.0, 0.0, float(width), float(height))
        now = self.clock()
        with self._lock:
            if (width, height) != self._frame_size:
                self._frame_size = (width, height)
                self._rect = None
            if target_id != self._target:
                self._target = target_id
                self._held = None
                self._last_seen = None
            subject = (
                next((o for o in observations if o.local_track_id == target_id), None)
                if target_id is not None
                else None
            )
            if subject is not None:
                self._held = framing_rect(
                    subject.bounding_box, width, height, self._fill, self.max_zoom
                )
                self._last_seen = now
            elif self._last_seen is None or now - self._last_seen > self.lost_hold_s:
                self._held = None
            self._locked = subject is not None
            desired = self._held or full
            current = self._rect or full
            dt = now - self._last_update if self._last_update is not None else math.inf
            alpha = 1.0 if self.smoothing_s <= 0 else 1.0 - math.exp(-dt / self.smoothing_s)
            self._rect = _lerp(current, desired, alpha)
            self._last_update = now
            return self._rect

    def apply(
        self,
        frame: np.ndarray,
        observations: Iterable[PersonObservation],
        target_id: int | None,
    ) -> np.ndarray:
        """Return `frame` cropped to the current zoom and resized to its original size."""
        height, width = frame.shape[:2]
        x1, y1, x2, y2 = self.update(frame.shape, observations, target_id)
        left, top = max(0, math.floor(x1)), max(0, math.floor(y1))
        right, bottom = min(width, math.ceil(x2)), min(height, math.ceil(y2))
        if right - left >= width and bottom - top >= height:
            return frame
        if right - left < 2 or bottom - top < 2:
            return frame
        crop = frame[top:bottom, left:right]
        return cv2.resize(crop, (width, height), interpolation=cv2.INTER_LINEAR)

    def status(self) -> dict:
        with self._lock:
            level = 1.0
            if self._rect is not None and self._frame_size is not None:
                level = self._frame_size[0] / max(1.0, self._rect[2] - self._rect[0])
            return {
                "target": self._target,
                "locked": self._locked,
                "holding": self._held is not None and not self._locked,
                "level": round(level, 2),
                "fill": self._fill,
            }
