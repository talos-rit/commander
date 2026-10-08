import argparse
import os
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import (
    BaseSettings,
    CliSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

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


type UIMode = Literal["simple", "debug"]
type DisplayMode = Literal["one_screen", "two_screen"]
type OneScreenMode = Literal["dynamic", "manual"]
type JogMode = Literal["discrete", "continuous"]


class AppSettingsFields(BaseModel):
    """
    Field definitions for AppSettings.

    Kept separate from the BaseSettings subclass so settings can be validated
    repeatedly at runtime; AppSettings() itself can only be built once per
    process because it registers its CLI flags on the shared ARG_PARSER.
    """

    model_config = ConfigDict(extra="ignore")

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

    # Web operator console (commander-web)
    web_host: str = Field(
        default="127.0.0.1", description="Interface the web UI server binds to"
    )
    web_port: int = Field(
        default=8000, ge=1, le=65535, description="Port the web UI server listens on"
    )
    # Debug is the default while the web UI is still in development.
    ui_mode: UIMode = Field(
        default="debug",
        description="simple shows only Home and Auto-Track; debug adds manual controls and telemetry",
    )
    display_mode: DisplayMode = Field(
        default="one_screen",
        description="Show one feed at a time or both camera feeds side by side",
    )
    one_screen_mode: OneScreenMode = Field(
        default="manual",
        description="In one-screen mode: pick the feed yourself (manual) or let Commander switch (dynamic)",
    )
    camera_1_host: str | None = Field(
        default=None,
        description="Robot config hostname shown as Camera 1 (the primary camera)",
    )
    camera_2_host: str | None = Field(
        default=None,
        description="Optional robot config hostname shown as Camera 2",
    )
    default_model: str | None = Field(
        default=None,
        description="Detection model to load when the web UI starts (None disables tracking CV)",
    )
    jog_mode: JogMode = Field(
        default="discrete",
        description="Manual jog style in debug mode",
    )


class AppSettings(AppSettingsFields, BaseSettings):
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
        from src.arg_parser import ARG_PARSER

        return (
            init_settings,
            CliSettingsSource(
                settings_cls, root_parser=ARG_PARSER, parse_args_method=_parse_args
            ),
            YamlConfigSettingsSource(settings_cls),
            dotenv_settings,
            env_settings,
        )
