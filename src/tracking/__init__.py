from importlib import import_module

from loguru import logger

from src.model_options import MODEL_OPTIONS, ModelOption

from .detector import ObjectModel
from .haar_cascade.basic_model import BasicModel

__all__ = ["ModelOption", "MODEL_OPTIONS", "USABLE_MODELS"]


USABLE_MODELS: dict[str, ObjectModel.__class__] = {}

# haar_cascade is imported via opencv-python by default
USABLE_MODELS["basic"] = BasicModel


def _register_optional_models(
    module_path: str,
    model_map: dict[ModelOption, str],
    feature_name: str,
    extra_name: str,
) -> None:
    try:
        module = import_module(module_path, package=__name__)
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
        ModelOption.MEDIAPIPEPOSE: "MediaPipeModel",
        ModelOption.MEDIAPIPE: "MediaPipePoseModel",
    },
    feature_name="mediapipe",
    extra_name="mediapipe",
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
)
