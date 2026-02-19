from enum import StrEnum

from loguru import logger

from src.directors import BaseDirector, ContinuousDirector

from .haar_cascade.basic_model import BasicModel
from .tracker import ObjectModel, Tracker


class ModelOption(StrEnum):
    YOLO_NANO = "yolo_nano"
    YOLO_SMALL = "yolo_small"
    YOLO_MEDIUM = "yolo_medium"
    YOLO_LARGE = "yolo_large"
    YOLO_XLARGE = "yolo_xlarge"
    MEDIAPIPE = "mediapipe"
    MEDIAPIPEPOSE = "mediapipepose"
    KEEPAWAY = "keepaway"
    BASIC = "basic"


USABLE_MODELS: dict[str, tuple[ObjectModel.__class__, BaseDirector.__class__]] = dict()

# haar_cascade is imported via opencv-python by default
USABLE_MODELS["basic"] = (BasicModel, ContinuousDirector)

try:
    from .media_pipe import MediaPipeModel, MediaPipePoseModel

    # USABLE_MODELS[ModelOption.KEEPAWAY] = (KeepAwayModel, KeepAwayDirector)
    USABLE_MODELS[ModelOption.MEDIAPIPEPOSE] = (MediaPipeModel, ContinuousDirector)
    USABLE_MODELS[ModelOption.MEDIAPIPE] = (MediaPipePoseModel, ContinuousDirector)
except ImportError as e:
    logger.warning(
        f"""{e}
        Failed to import mediapipe. This is an optional import, but may limit the ability to run this model.
        This can be installed using `uv sync --extra mediapipe` or `uv sync --all-extras`"""
    )

try:
    from .yolo.model import (
        YOLOLargeModel,
        YOLOMediumModel,
        YOLONanoModel,
        YOLOSmallModel,
        YOLOXLargeModel,
    )

    USABLE_MODELS[ModelOption.YOLO_NANO] = (YOLONanoModel, ContinuousDirector)
    USABLE_MODELS[ModelOption.YOLO_SMALL] = (YOLOSmallModel, ContinuousDirector)
    USABLE_MODELS[ModelOption.YOLO_MEDIUM] = (YOLOMediumModel, ContinuousDirector)
    USABLE_MODELS[ModelOption.YOLO_LARGE] = (YOLOLargeModel, ContinuousDirector)
    USABLE_MODELS[ModelOption.YOLO_XLARGE] = (YOLOXLargeModel, ContinuousDirector)
except ImportError as e:
    logger.warning(
        f"""{e}
        Failed to import Yolo model. This is an optional import, but may limit the ability to run this model.
        This can be installed using `uv sync --extra yolo` or `uv sync --all-extras`"""
    )

MODEL_OPTIONS = list(USABLE_MODELS.keys())

__all__ = ["USABLE_MODELS", "ModelOption", "MODEL_OPTIONS", "Tracker"]
