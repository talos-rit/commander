from enum import StrEnum
from importlib.util import find_spec


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


def _has_module(module_name: str) -> bool:
    return find_spec(module_name) is not None


def get_usable_model_options() -> list[str]:
    options = [ModelOption.BASIC.value]

    if _has_module("mediapipe"):
        options.extend(
            [
                ModelOption.MEDIAPIPEPOSE.value,
                ModelOption.MEDIAPIPE.value,
            ]
        )

    if _has_module("torch") and _has_module("ultralytics"):
        options.extend(
            [
                ModelOption.YOLO_NANO.value,
                ModelOption.YOLO_SMALL.value,
                ModelOption.YOLO_MEDIUM.value,
                ModelOption.YOLO_LARGE.value,
                ModelOption.YOLO_XLARGE.value,
            ]
        )

    return options


MODEL_OPTIONS = get_usable_model_options()
