from enum import StrEnum

from .tracker import ObjectModel


class ModelOption(StrEnum):
    YOLO = "yolo"
    STANDARD = "standard"
    MEDIAPIPEPOSE = "mediapipepose"
    KEEPAWAY = "keepaway"


MODEL_OPTIONS = list(map(lambda v: v.value, list(ModelOption)))


MODELS: dict[str, ObjectModel.__class__] = dict()


try:
    from .haar_cascade.basic_model import BasicModel

    # Test if this model works
    MODELS["basic"] = BasicModel
except ImportError as e:
    print(
        e,
        "Failed to import Haar cascade. This is an optional import, but may limit the ability to run this model",
    )

try:
    from .keep_away.keep_away_model import KeepAwayModel
    from .media_pipe import MediaPipeModel, MediaPipePoseModel

    MODELS[ModelOption.KEEPAWAY] = KeepAwayModel
    MODELS[ModelOption.MEDIAPIPEPOSE] = MediaPipeModel
    MODELS[ModelOption.STANDARD] = MediaPipePoseModel
except ImportError as e:
    print(
        e,
        "Failed to import mediapipe. This is an optional import, but may limit the ability to run this model",
    )

try:
    from .yolo.yolo_model import YOLOModel

    MODELS[ModelOption.YOLO] = YOLOModel
except ImportError as e:
    print(
        e,
        "Failed to import Yolo model. This is an optional import, but may limit the ability to run this model",
    )

__all__ = ["MODELS", "ModelOption", "MODEL_OPTIONS"]
