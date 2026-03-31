from __future__ import annotations

from enum import StrEnum
from importlib import import_module
from importlib.util import find_spec
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from .detector import ObjectModel
from .haar_cascade.basic_model import BasicModel


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


USABLE_MODELS: dict[str, ObjectModel.__class__] = {}

# haar_cascade is imported via opencv-python by default
USABLE_MODELS["basic"] = BasicModel


def _register_optional_models(
    module_path: str,
    model_map: dict[ModelOption, str],
    feature_name: str,
    extra_name: str,
    dependency: list[str] = [],
) -> None:
    if any(find_spec(dep) is None for dep in dependency):
        logger.warning(
            f"""One or more dependencies for {feature_name} are not installed. 
            Failed to import {feature_name}. This is an optional import, but may limit the ability to run this model.
            This can be installed using `uv sync --extra {extra_name}` or `uv sync --all-extras`"""
        )
        return
    try:
        module = import_module(module_path, package=__package__)
        for option, class_name in model_map.items():
            USABLE_MODELS[option] = getattr(module, class_name)
    except ModuleNotFoundError as e:
        logger.warning(
            f"""{e}
            Failed to import {feature_name}. This is an optional import, but may limit the ability to run this model.
            This can be installed using `uv sync --extra {extra_name}` or `uv sync --all-extras`"""
        )
    except Exception:
        logger.exception(f"Failed to initialize optional model package: {module_path}")


_register_optional_models(
    ".media_pipe",
    {
        # USABLE_MODELS[ModelOption.KEEPAWAY] = (KeepAwayModel, KeepAwayDirector)
        # ModelOption.MEDIAPIPE: "MediaPipePoseModel",
        ModelOption.MEDIAPIPEPOSE: "MediaPipeModel",
    },
    feature_name="mediapipe",
    extra_name="mediapipe",
    dependency=["mediapipe"],
)

_register_optional_models(
    ".yolo.model",
    {
        ModelOption.YOLO_NANO: "YOLONanoModel",
        ModelOption.YOLO_SMALL: "YOLOSmallModel",
        ModelOption.YOLO_MEDIUM: "YOLOMediumModel",
        ModelOption.YOLO_LARGE: "YOLOLargeModel",
        ModelOption.YOLO_XLARGE: "YOLOXLargeModel",
    },
    feature_name="Yolo model",
    extra_name="yolo",
    dependency=["torch", "ultralytics"],
)
MODEL_OPTIONS = list(USABLE_MODELS.keys())
