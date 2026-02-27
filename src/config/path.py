import os

from src.utils import get_file_path

ROBOT_CONFIGS_PATH = get_file_path(
    os.path.join(os.path.dirname(__file__), "../../config/robot_configs.local.yaml")
)
DEFAULT_PATH = get_file_path(
    os.path.join(os.path.dirname(__file__), "../../config/example_default_config.yaml")
)
LOCAL_DEFAULT_PATH = get_file_path(
    os.path.join(os.path.dirname(__file__), "../../config/default_config.local.yaml")
)
APP_SETTINGS_PATH = get_file_path(
    os.path.join(os.path.dirname(__file__), "../../config/app_settings.yaml")
)
APP_SETTINGS_DEFAULT_PATH = get_file_path(
    os.path.join(os.path.dirname(__file__), "../../config/app_settings.default.yaml")
)
