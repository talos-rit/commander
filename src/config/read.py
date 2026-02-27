import os
from typing import Any

import yaml

from src.config.path import (
    APP_SETTINGS_DEFAULT_PATH,
    APP_SETTINGS_PATH,
    DEFAULT_PATH,
    LOCAL_DEFAULT_PATH,
    ROBOT_CONFIGS_PATH,
)


def read_default_robot_config() -> dict[str, Any]:
    """
    Load the default configuration from config/default_config.yaml or
    config/default_config.local.yaml if it exists.
    """
    if os.path.exists(LOCAL_DEFAULT_PATH):
        with open(LOCAL_DEFAULT_PATH, "r") as f:
            default_config = yaml.safe_load(f)
    else:
        with open(DEFAULT_PATH, "r") as f:
            default_config = yaml.safe_load(f)
    return default_config


def read_robot_config_file() -> dict[str, dict]:
    """
    Load the robot configuration from config/config.local.yaml if it exists,
    otherwise from config/config.yaml. Returns a dictionary of raw config data.
    """
    if os.path.exists(ROBOT_CONFIGS_PATH):
        with open(ROBOT_CONFIGS_PATH, "r") as f:
            return yaml.safe_load(f) or {}
    else:
        return {}


def read_app_settings() -> dict[str, Any]:
    """
    Load the app settings from config/app_settings.yaml. Returns a dictionary of raw app settings data.
    """
    if not os.path.exists(APP_SETTINGS_PATH):
        # Copy default app settings to app settings path if it doesn't exist
        with open(APP_SETTINGS_DEFAULT_PATH, "r") as f:
            default_app_settings = yaml.safe_load(f) or {}
        with open(APP_SETTINGS_PATH, "w") as f:
            yaml.safe_dump(default_app_settings, f)
    with open(APP_SETTINGS_PATH, "r") as f:
        return yaml.safe_load(f) or {}
