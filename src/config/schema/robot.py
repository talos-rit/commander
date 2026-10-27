"""
Pydantic-based configuration schema for Talos application.
Provides type validation, range checking, and default values for all configuration fields.
"""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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
    pi_vision_url: Optional[str] = Field(default=None, description="PiVision local tracking and manual gateway URL; Commander supervises control")
    pi_vision_max_age_s: float = Field(default=0.35, ge=0.05, le=1.0)
    pi_vision_speed_percent: int = Field(default=20, ge=1, le=100)

    @field_validator("pi_vision_url")
    @classmethod
    def validate_pi_vision_url(cls, value):
        if value is not None:
            from urllib.parse import urlsplit
            parsed = urlsplit(value)
            if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise ValueError("PiVision URL must be an HTTP(S) service URL without credentials, query or fragment")
        return value

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

    # Vertical auto-track. Fixed order: elbow, then shoulder, then polar up/down.
    # Defaults keep existing robots on polar up/down only.
    track_elbow: bool = Field(
        default=False,
        description="Auto-Track may jog the elbow for vertical image error",
    )
    track_shoulder: bool = Field(
        default=False,
        description="Auto-Track may jog the shoulder after the elbow cannot move further",
    )
    track_polar_vertical: bool = Field(
        default=True,
        description="Auto-Track may polar-pan up/down after elbow and shoulder",
    )
    elbow_count_min: Optional[int] = Field(
        default=None, description="Fresh elbow count at or below this skips to the next vertical axis"
    )
    elbow_count_max: Optional[int] = Field(default=None)
    shoulder_count_min: Optional[int] = Field(default=None)
    shoulder_count_max: Optional[int] = Field(default=None)
    pitch_count_min: Optional[int] = Field(default=None)
    pitch_count_max: Optional[int] = Field(default=None)

    @model_validator(mode="after")
    def validate_count_limits(self):
        pairs = (
            ("elbow_count_min", "elbow_count_max"),
            ("shoulder_count_min", "shoulder_count_max"),
            ("pitch_count_min", "pitch_count_max"),
        )
        for low_name, high_name in pairs:
            low, high = getattr(self, low_name), getattr(self, high_name)
            if (low is None) != (high is None):
                raise ValueError(f"{low_name} and {high_name} must be set together")
            if low is not None and low >= high:
                raise ValueError(f"{low_name} must be less than {high_name}")
        return self

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


type RobotConfigs = dict[str, ConnectionConfig]
