"""
Pydantic-based configuration schema for Talos application.
Provides type validation, range checking, and default values for all configuration fields.
"""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AppSettings(BaseModel):
    """
    Application-wide settings that are not specific to individual connections.
    """

    log_level: str = Field(
        default="INFO",
        description="Logging level (e.g., DEBUG, INFO, WARNING, ERROR)",
    )


class ConnectionConfig(BaseModel):
    """
    Configuration for a single robot arm connection.
    Validates types, ranges, and logical constraints.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    socket_host: str = Field(
        ..., description="IP address or hostname of the robot operator"
    )
    socket_port: int = Field(
        ...,
        description="Socket port for robot operator communication",
        ge=1,
        le=65535,
    )
    camera_index: int | str = Field(
        ...,
        description="Camera device index (0, 1, ...) or URL (RTSP/HTTP stream)",
    )

    # Tracking parameters
    acceptable_box_percent: float = Field(
        default=0.4,
        description="Percentage of frame used for acceptable box (0.0 to 1.0)",
        ge=0.01,
        le=1.0,
    )
    vertical_field_of_view: int = Field(
        default=48,
        description="Vertical FOV of camera in degrees",
        ge=1,
        le=180,
    )
    horizontal_field_of_view: int = Field(
        default=89,
        description="Horizontal FOV of camera in degrees",
        ge=1,
        le=180,
    )
    confirmation_delay: float = Field(
        default=0.25,
        description="Seconds to wait before sending command when subject moves outside acceptable box",
        ge=0.0,
        le=10.0,
    )

    # Command timing
    command_delay: float = Field(
        default=0.25,
        description="Seconds between discrete directional commands",
        ge=0.0,
        le=10.0,
    )

    # Display parameters
    fps: int = Field(
        default=30,
        description="Target frame rate for UI display",
        ge=1,
        le=240,
    )
    frame_width: int = Field(
        default=500,
        description="Desired width of video frames in pixels",
        ge=160,
        le=4096,
    )
    frame_height: Optional[int] = Field(
        default=None,
        description="Desired height of video frames (auto-calculated if None)",
    )

    max_fps: int = Field(
        default=40,
        description="Maximum FPS for bounding box polling",
        ge=1,
        le=240,
    )

    # Control mode
    manual_only: bool = Field(
        default=False, description="If True, only manual control is allowed"
    )

    @field_validator("camera_index", mode="before")
    @classmethod
    def validate_camera_index(cls, v):
        """Allow integer device index or string URL."""
        if isinstance(v, int):
            if v < 0:
                raise ValueError("Camera device index must be >= 0")
            return v
        if isinstance(v, str):
            if v.strip() == "":
                raise ValueError("Camera URL cannot be empty string")
            return v
        raise ValueError(f"Camera index must be int or str, got {type(v)}")
