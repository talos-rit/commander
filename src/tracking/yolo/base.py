from enum import StrEnum
from os import path

import numpy as np
import torch
from loguru import logger
from ultralytics import YOLO  # pyright: ignore[reportPrivateImportUsage]
from ultralytics.engine.model import Model  # pyright: ignore[reportPrivateImportUsage]

from assets import join_paths
from src.tracking.detector import ObjectModel
from src.tracking.types import BBox

HUMAN_DETECTION_CLASS_ID = 0


class YOLOModelSize(StrEnum):
    NANO = "nano"
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"
    XLARGE = "xlarge"

    @property
    def pt_file(self):
        return {
            YOLOModelSize.NANO: "yolo26n.pt",
            YOLOModelSize.SMALL: "yolo26s.pt",
            YOLOModelSize.MEDIUM: "yolo26m.pt",
            YOLOModelSize.LARGE: "yolo26l.pt",
            YOLOModelSize.XLARGE: "yolo26x.pt",
        }[self]

    @property
    def pose_pt_file(self):
        return {
            YOLOModelSize.NANO: "yolo26n-pose.pt",
            YOLOModelSize.SMALL: "yolo26s-pose.pt",
            YOLOModelSize.MEDIUM: "yolo26m-pose.pt",
            YOLOModelSize.LARGE: "yolo26l-pose.pt",
            YOLOModelSize.XLARGE: "yolo26x-pose.pt",
        }[self]


def get_device():
    return (
        "cuda:0"
        if torch.cuda.is_available()
        else "mps"
        if torch.backends.mps.is_available()
        else "cpu"
    )


class YOLOBaseModel(ObjectModel):
    model_size: YOLOModelSize = YOLOModelSize.MEDIUM
    speaker_color: int | None = None

    # The tracker class is responsible for capturing frames from the source and detecting people in the frames
    def __init__(
        self,
        _yolo_pt_dir=join_paths("yolo"),
        _pt_file: str | None = None,
    ):
        self.speaker_bbox = None  # Shared reference. Only here to avoid pylint errors.
        self.device = get_device()
        logger.info(f"Using YOLO model size: {self.model_size}, device: {self.device}")
        self.object_detector: Model = YOLO(
            path.join(_yolo_pt_dir, _pt_file or self.model_size.pt_file), verbose=False
        )

    def detect_person(self, frame, *_) -> list[BBox]:
        (detection_result,) = self.object_detector.track(
            frame,
            classes=HUMAN_DETECTION_CLASS_ID,
            device=self.device,
            verbose=False,
            persist=True,
        )
        if detection_result is None or detection_result.boxes is None:
            return []
        ids = detection_result.boxes.id  # ndarray
        xyxy = detection_result.boxes.xyxy  # ndarray
        if ids is None or xyxy is None:
            return self.to_numpy(xyxy).astype(int).tolist() if xyxy is not None else []
        sorted_idx = np.argsort(ids.flatten())
        sorted_xyxy = self.to_numpy(xyxy[sorted_idx]).astype(int).tolist()
        return sorted_xyxy

    def to_numpy(self, tensor_or_array):
        if hasattr(tensor_or_array, "numpy"):
            return tensor_or_array.numpy()
        return np.asarray(tensor_or_array)
