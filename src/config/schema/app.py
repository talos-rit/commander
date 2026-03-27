import argparse
import os
from typing import Literal

from pydantic import Field
from pydantic_settings import (
    BaseSettings,
    CliSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

from src.arg_parser import ARG_PARSER
from src.config.path import APP_SETTINGS_DEFAULT_PATH, APP_SETTINGS_PATH


def _parse_args(root_parser: argparse.ArgumentParser, args) -> argparse.Namespace:
    """
    Implement overrides for App Settings that are triggered by providing certain cli args

    Returns:
        Namespace: arguments parsed from the command line, with any necessary overrides applied.
    """
    args = root_parser.parse_args(args)
    if args.debug:
        args.log_level = "DEBUG"
        args.draw_bboxes = True
    return args


class AppSettings(BaseSettings):
    """
    Application-wide settings that are not specific to individual connections.
    """

    model_config = SettingsConfigDict(
        env_prefix="COMMANDER_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        yaml_file=APP_SETTINGS_PATH
        if os.path.exists(APP_SETTINGS_PATH)
        else APP_SETTINGS_DEFAULT_PATH,
        yaml_file_encoding="utf-8",
        cli_parse_args=True,
        cli_kebab_case=True,
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            CliSettingsSource(
                settings_cls, root_parser=ARG_PARSER, parse_args_method=_parse_args
            ),
            YamlConfigSettingsSource(settings_cls),
            dotenv_settings,
            env_settings,
        )

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Logging level (e.g., DEBUG, INFO, WARNING, ERROR)",
    )
    bbox_max_fps: int = Field(
        default=30,
        description="Maximum frames per second for pulling bounding box data (can be adjusted down if scheduler is overloaded)",
    )
    frame_process_fps: int = Field(
        default=30,
        description="Frames per second for pulling video streams (can be lower than max_fps to reduce load)",
    )
    disable_performance_warnings: bool = Field(
        default=False,
        description="Whether to disable warnings about performance issues (e.g., if processing is taking too long and frames are being dropped or the opposite)",
    )
