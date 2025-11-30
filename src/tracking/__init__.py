from enum import StrEnum

from src.directors import BaseDirector, ContinuousDirector

from .haar_cascade.basic_model import BasicModel
from .keep_away.keep_away_director import KeepAwayDirector
from .tracker import ObjectModel, Tracker


class ModelOption(StrEnum):
    YOLO = "yolo"
    MEDIAPIPE = "mediapipe"
    MEDIAPIPEPOSE = "mediapipepose"
    KEEPAWAY = "keepaway"
    BASIC = "basic"


USABLE_MODELS: dict[str, tuple[ObjectModel.__class__, BaseDirector.__class__]] = dict()

# haar_cascade is imported via opencv-python by default
USABLE_MODELS["basic"] = (BasicModel, ContinuousDirector)

try:
    from .keep_away.keep_away_model import KeepAwayModel
    from .media_pipe import MediaPipeModel, MediaPipePoseModel

    USABLE_MODELS[ModelOption.KEEPAWAY] = (KeepAwayModel, KeepAwayDirector)
    USABLE_MODELS[ModelOption.MEDIAPIPEPOSE] = (MediaPipeModel, ContinuousDirector)
    USABLE_MODELS[ModelOption.MEDIAPIPE] = (MediaPipePoseModel, ContinuousDirector)
except ImportError as e:
    print(
        e,
        "Failed to import mediapipe. This is an optional import, but may limit the ability to run this model",
        "This can be installed using `uv sync --extra mediapipe` or `uv sync --extra all`",
    )

try:
    from .yolo.yolo_model import YOLOModel

    USABLE_MODELS[ModelOption.YOLO] = (YOLOModel, ContinuousDirector)
except ImportError as e:
    print(
        e,
        "Failed to import Yolo model. This is an optional import, but may limit the ability to run this model",
        "This can be installed using `uv sync --extra yolo` or `uv sync --extra all`",
    )

MODEL_OPTIONS = list(USABLE_MODELS.keys())

__all__ = ["USABLE_MODELS", "ModelOption", "MODEL_OPTIONS", "Tracker"]
