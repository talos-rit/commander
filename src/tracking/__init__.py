from loguru import logger
from src.model_options import MODEL_OPTIONS, ModelOption

from .detector import ObjectModel
from .haar_cascade.basic_model import BasicModel

__all__ = ["ModelOption", "MODEL_OPTIONS", "USABLE_MODELS"]


USABLE_MODELS: dict[str, ObjectModel.__class__] = dict()

# haar_cascade is imported via opencv-python by default
USABLE_MODELS["basic"] = BasicModel

try:
    from .media_pipe import MediaPipeModel, MediaPipePoseModel

    # USABLE_MODELS[ModelOption.KEEPAWAY] = (KeepAwayModel, KeepAwayDirector)
    USABLE_MODELS[ModelOption.MEDIAPIPEPOSE] = MediaPipeModel
    USABLE_MODELS[ModelOption.MEDIAPIPE] = MediaPipePoseModel
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

    USABLE_MODELS[ModelOption.YOLO_NANO] = YOLONanoModel
    USABLE_MODELS[ModelOption.YOLO_SMALL] = YOLOSmallModel
    USABLE_MODELS[ModelOption.YOLO_MEDIUM] = YOLOMediumModel
    USABLE_MODELS[ModelOption.YOLO_LARGE] = YOLOLargeModel
    USABLE_MODELS[ModelOption.YOLO_XLARGE] = YOLOXLargeModel
except ImportError as e:
    logger.warning(
        f"""{e}
        Failed to import Yolo model. This is an optional import, but may limit the ability to run this model.
        This can be installed using `uv sync --extra yolo` or `uv sync --all-extras`"""
    )


