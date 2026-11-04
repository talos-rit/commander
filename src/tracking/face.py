"""Face embeddings from OpenCV's YuNet detector and SFace recognizer.

Faces identify people across clothing changes, but only when one is visible
and big enough, so these complement body embeddings rather than replace them.
"""

import os
import urllib.request
from collections.abc import Sequence

import cv2
import numpy as np
from loguru import logger

from assets import join_paths
from src.observations.types import BBox

MODELS_URL = "https://github.com/opencv/opencv_zoo/raw/main/models"
DETECTOR = "face_detection_yunet/face_detection_yunet_2023mar.onnx"
RECOGNIZER = "face_recognition_sface/face_recognition_sface_2021dec.onnx"

HEAD_SHARE = 0.5
"""Top share of a person box searched for their face. Covers both full-body
boxes, where the head is near the top, and webcam boxes that end at the chest."""
MIN_FACE_PX = 40
"""Smaller faces are too blurry for SFace to tell apart."""
MIN_FACE_SCORE = 0.8
DETECT_PX = 320
"""Longest side the head crop is shrunk to for face detection."""


def model_path(name: str) -> str:
    """Path to an opencv_zoo model in assets/face, downloaded on first use."""
    path = join_paths("face", os.path.basename(name))
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        logger.info("Downloading {}", os.path.basename(name))
        partial = f"{path}.part"
        with urllib.request.urlopen(f"{MODELS_URL}/{name}", timeout=60) as response, open(partial, "wb") as out:
            while chunk := response.read(1 << 20):
                out.write(chunk)
        os.replace(partial, path)
    return path


class SFaceEmbedder:
    """One SFace vector per person box, or None where no clear face shows."""

    def __init__(self, detector: str | None = None, recognizer: str | None = None):
        self._detector = cv2.FaceDetectorYN.create(
            detector or model_path(DETECTOR), "", (320, 320), MIN_FACE_SCORE
        )
        self._recognizer = cv2.FaceRecognizerSF.create(recognizer or model_path(RECOGNIZER), "")

    def embed(self, image: np.ndarray, boxes: Sequence[BBox]) -> list[np.ndarray | None]:
        return [self._embed_one(image, box) for box in boxes]

    def _embed_one(self, image: np.ndarray, box: BBox) -> np.ndarray | None:
        height, width = image.shape[:2]
        x1, y1 = max(0, int(box[0])), max(0, int(box[1]))
        x2 = min(width, int(box[2]))
        y2 = min(height, int(box[1] + (box[3] - box[1]) * HEAD_SHARE))
        if x2 - x1 < MIN_FACE_PX or y2 - y1 < MIN_FACE_PX:
            return None
        head = np.ascontiguousarray(image[y1:y2, x1:x2])
        # Detect on a small copy; YuNet's cost grows with pixels, SFace aligns at full size.
        scale = min(1.0, DETECT_PX / max(head.shape[:2]))
        small = head if scale == 1.0 else cv2.resize(head, None, fx=scale, fy=scale)
        self._detector.setInputSize((small.shape[1], small.shape[0]))
        _, faces = self._detector.detect(small)
        if faces is None:
            return None
        faces[:, :14] /= scale  # box and five landmarks; column 14 is the score
        faces = faces[faces[:, 2] >= MIN_FACE_PX]
        if len(faces) == 0:
            return None
        # The face most centered over the box is the person's own; overlapping
        # boxes often take in a neighbor's face near one side.
        middle = (box[0] + box[2]) / 2 - x1
        face = faces[np.argmin(np.abs(faces[:, 0] + faces[:, 2] / 2 - middle))]
        aligned = self._recognizer.alignCrop(head, face)
        return self._recognizer.feature(aligned).ravel().astype(np.float32)
