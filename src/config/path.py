import os

from src.utils import get_file_path

_CONFIG_DIR = os.path.join(os.path.dirname(__file__), "../../config")
ROBOT_CONFIG_FILENAME = "robot_configs.local.yaml"
ROBOT_CONFIGS_PATH = get_file_path(os.path.join(_CONFIG_DIR, ROBOT_CONFIG_FILENAME))
EXAMPLE_DEFAULT_ROBOT_CONFIG_FILENAME = "example_default_configs.yaml"
EXAMPLE_DEFAULT_ROBOT_CONFIG_PATH = get_file_path(
    os.path.join(_CONFIG_DIR, EXAMPLE_DEFAULT_ROBOT_CONFIG_FILENAME)
)
DEFAULT_ROBOT_CONFIG_FILENAME = "default_config.local.yaml"
DEFAULT_ROBOT_CONFIG_PATH = get_file_path(
    os.path.join(_CONFIG_DIR, DEFAULT_ROBOT_CONFIG_FILENAME)
)
APP_SETTINGS_FILENAME = "app_settings.local.yaml"
APP_SETTINGS_PATH = get_file_path(os.path.join(_CONFIG_DIR, APP_SETTINGS_FILENAME))
APP_SETTINGS_DEFAULT_FILENAME = "app_settings.yaml"
APP_SETTINGS_DEFAULT_PATH = get_file_path(
    os.path.join(_CONFIG_DIR, APP_SETTINGS_DEFAULT_FILENAME)
)
BACKUP_DIR = get_file_path(
    os.path.join(os.path.dirname(__file__), "../../config/backups")
)
