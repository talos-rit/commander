from pydantic import BaseModel, Field


class AppSettings(BaseModel):
    """
    Application-wide settings that are not specific to individual connections.
    """

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
