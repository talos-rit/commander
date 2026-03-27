import math
from enum import StrEnum
from os import path

import torch
from loguru import logger
from ultralytics import YOLO  # pyright: ignore[reportPrivateImportUsage]
from ultralytics.engine.model import Model  # pyright: ignore[reportPrivateImportUsage]

from assets import join_paths
from src.tracking.detector import ObjectModel
from src.tracking.types import BBox, Frame

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


class YOLOBaseModel(ObjectModel):
    model_size: YOLOModelSize = YOLOModelSize.MEDIUM
    speaker_color: int | None = None
    color_threshold: int = 15
    lost_threshold: int = 300

    # The tracker class is responsible for capturing frames from the source and detecting people in the frames
    def __init__(
        self,
        _yolo_pt_dir=join_paths("yolo"),
        _pt_file: str | None = None,
        _pt_pose_file: str | None = None,
    ):
        self.speaker_bbox = None  # Shared reference. Only here to avoid pylint errors.
        self.device = (
            "cuda:0"
            if torch.cuda.is_available()
            else "mps"
            if torch.backends.mps.is_available()
            else "cpu"
        )
        logger.info(f"Using YOLO model size: {self.model_size}, device: {self.device}")
        self.object_detector: Model = YOLO(
            path.join(_yolo_pt_dir, _pt_file or self.model_size.pt_file), verbose=False
        )
        self.lost_counter = 0

    def size_32_determiner(self, frame, inHeight, inWidth=None) -> Frame:
        """
        The formula will find the closest multiple of 32 for the given size.
        YOLO model requires input sizes to be multiples of 32, so we determine the frame size based on that requirement.
        """
        h, w = self.determine_frame_size(frame, inHeight, inWidth)
        return (math.ceil(h / 32) * 32, math.ceil(w / 32) * 32)

    def detect_person(self, frame, inHeight=500, inWidth=None) -> list[BBox]:
        frameRGB, metadata = self.resize_frame(
            frame, inHeight, inWidth, self.size_32_determiner
        )
        logger.debug(metadata)
        detection_result = self.object_detector(
            frameRGB,
            classes=HUMAN_DETECTION_CLASS_ID,
            verbose=False,
            imgsz=metadata.size,
            device=self.device,
        )[0]
        return [
            self.fix_bbox_scale(xyxy, metadata) for xyxy in detection_result.boxes.xyxy
        ]
