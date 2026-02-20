"""
Configuration loading and management for Talos application.
Supports both raw YAML dict access and validated Pydantic models.
"""

from pydantic import ValidationError
from loguru import logger
from src.config.read import read_default_robot_config, read_robot_config_file
from src.config.schema import ConnectionConfig


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
