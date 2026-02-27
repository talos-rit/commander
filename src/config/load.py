"""
Configuration loading and management for Talos application.
Supports both raw YAML dict access and validated Pydantic models.
"""

from pprint import pprint
from typing import Callable

from loguru import logger
from pydantic import ValidationError

from src.config.read import (
    app_settings_recovery,
    read_app_settings,
    read_default_robot_config,
    read_robot_config_file,
)
from src.config.schema.robot import ConnectionConfig

from .schema.app import AppSettings


def load_app_settings(
    _recovery_method: Callable[[], AppSettings] = app_settings_recovery,
) -> AppSettings:
    """
    Load the app settings from settings file. If it does not it exist it will run a recovery method.

    Returns:
        AppSettings: A validated AppSettings object with the loaded settings.
    """
    try:
        settings = AppSettings(**read_app_settings())
        print("App settings loaded successfully")
        pprint(settings.model_dump_json(indent=2))
        return settings
    except ValidationError as e:
        print(
            "Invalid app settings in app_settings.yaml, using hardcoded defaults\n"
            + str(e)
        )
        yon = input(
            "Press Enter to continue with defaults, or fix app_settings.yaml and restart the app.(y/N)"
        )
        if yon.strip().lower() != "y":
            raise e
    except FileNotFoundError as e:
        print("app_settings.yaml not found creating settings file\n" + str(e))
    return _recovery_method()


APP_SETTINGS = load_app_settings()


def load_default_robot_config() -> ConnectionConfig:
    """
    Load the default robot configuration from config/default_config.yaml or
    config/default_config.local.yaml if it exists. Returns a validated
    ConnectionConfig object with default values.
    """

    try:
        return ConnectionConfig(**read_default_robot_config())
    except ValidationError as e:
        logger.error(
            "Invalid default configuration in default_config.yaml, using hardcoded defaults"
            + str(e)
        )
        raise e


DEFAULT_ROBOT_CONFIG = load_default_robot_config()


def load_robot_config() -> dict[str, ConnectionConfig]:
    """
    Load and validate configuration from config/config.local.yaml.
    Converts each host entry to a validated ConnectionConfig object.
    Missing or invalid configs logged as warnings; skipped with defaults available.

    Returns:
        Dictionary mapping hostname to validated ConnectionConfig objects.
        Only includes successfully validated configs.
    """
    raw_config = read_robot_config_file()
    validated_config = {}

    for hostname, config_data in raw_config.items():
        try:
            # Create validated config, using defaults for optional fields
            validated_config[hostname] = ConnectionConfig(
                **{
                    **DEFAULT_ROBOT_CONFIG.model_dump(),
                    **config_data,
                }
            )
        except ValidationError as e:
            logger.warning(
                f"Invalid configuration for '{hostname}' in config.local.yaml, skipping\n"
                + str(e)
            )
            continue
    return validated_config


ROBOT_CONFIGS = load_robot_config()
