import os
from typing import Any

import yaml

import src.config as global_config
from src.config.path import APP_SETTINGS_PATH, ROBOT_CONFIGS_PATH
from src.config.read import read_robot_config_file
from src.config.schema.app import AppSettings, AppSettingsFields
from src.config.schema.robot import ConnectionConfig


def _read_yaml(path: str) -> dict[str, Any]:
    if not os.path.exists(path):
        return {}
    with open(path, "r") as f:
        return yaml.safe_load(f) or {}


def _write_yaml(path: str, data: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w") as f:
        yaml.safe_dump(data, f, sort_keys=False)
    os.replace(tmp_path, path)


def save_app_settings(updates: dict[str, Any]) -> AppSettings:
    """
    Validate and persist app setting changes to app_settings.local.yaml, then
    apply them to the in-memory APP_SETTINGS so callers see them immediately.

    Only the updated keys are written on top of the existing local file, so CLI
    and environment overrides active for this run are not baked into the file.

    Raises:
        pydantic.ValidationError: if the merged settings are invalid.
    """
    current = global_config.APP_SETTINGS
    validated = AppSettingsFields.model_validate({**current.model_dump(), **updates})
    file_data = _read_yaml(APP_SETTINGS_PATH)
    changed = {key: getattr(validated, key) for key in updates}
    _write_yaml(APP_SETTINGS_PATH, {**file_data, **changed})
    new_settings = AppSettings.model_construct(**validated.model_dump())
    global_config.APP_SETTINGS = new_settings
    return new_settings


def update_config(hostname: str, connection_config: ConnectionConfig) -> None:
    """
    Replace (or create) the robot config stored under `hostname` in
    robot_configs.local.yaml and in the in-memory ROBOT_CONFIGS.
    """
    raw = read_robot_config_file()
    raw[hostname] = connection_config.model_dump()
    _write_yaml(ROBOT_CONFIGS_PATH, raw)
    global_config.ROBOT_CONFIGS[hostname] = connection_config


def remove_config(hostname: str) -> bool:
    """Delete a robot config entry. Returns False if it did not exist."""
    raw = read_robot_config_file()
    existed = hostname in raw or hostname in global_config.ROBOT_CONFIGS
    raw.pop(hostname, None)
    _write_yaml(ROBOT_CONFIGS_PATH, raw)
    global_config.ROBOT_CONFIGS.pop(hostname, None)
    return existed
