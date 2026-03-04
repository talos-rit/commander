import os

from pydantic import Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    YamlConfigSettingsSource,
    SettingsConfigDict,
)

from src.config.path import APP_SETTINGS_DEFAULT_PATH, APP_SETTINGS_PATH


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
        yaml_file=APP_SETTINGS_PATH if os.path.exists(APP_SETTINGS_PATH) else APP_SETTINGS_DEFAULT_PATH,
        yaml_file_encoding="utf-8",
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
            env_settings,
            dotenv_settings,
            init_settings,
            YamlConfigSettingsSource(settings_cls),
        )

    log_level: str = Field(
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
