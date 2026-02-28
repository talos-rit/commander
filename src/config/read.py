import os
import shutil
from typing import Any

import yaml

from src.config.path import (
    APP_SETTINGS_DEFAULT_PATH,
    APP_SETTINGS_PATH,
    DEFAULT_PATH,
    LOCAL_DEFAULT_PATH,
    ROBOT_CONFIGS_PATH,
)
from src.config.schema.app import AppSettings


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
    with open(APP_SETTINGS_PATH, "r") as f:
        return yaml.safe_load(f) or {}


def app_settings_recovery() -> AppSettings:
    if os.path.exists(APP_SETTINGS_PATH):
        if os.path.exists(APP_SETTINGS_PATH + ".backup"):
            file_num = 1
            while os.path.exists(APP_SETTINGS_PATH + ".backup" + str(file_num)):
                file_num += 1
            path = shutil.copy(
                APP_SETTINGS_PATH, APP_SETTINGS_PATH + f".backup{file_num}"
            )
        else:
            path = shutil.copy(APP_SETTINGS_PATH, APP_SETTINGS_PATH + ".backup")
        print(f"Backed up existing app settings to {path}")
        os.remove(APP_SETTINGS_PATH)
    # Copy default app settings to app settings path if it doesn't exist
    with open(APP_SETTINGS_DEFAULT_PATH, "r") as f:
        default_app_settings = yaml.safe_load(f) or {}
    with open(APP_SETTINGS_PATH, "w") as f:
        yaml.safe_dump(default_app_settings, f)
    # Try loading again after recovery
    try:
        return AppSettings(**read_app_settings())
    except Exception as e:
        print(
            "Failed to recover valid app settings from defaults. Please check app_settings.yaml for issues.\n"
        )
        raise e
