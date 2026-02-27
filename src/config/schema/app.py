from pydantic import BaseModel, Field


class AppSettings(BaseModel):
    """
    Application-wide settings that are not specific to individual connections.
    """

    log_level: str = Field(
        default="INFO",
        description="Logging level (e.g., DEBUG, INFO, WARNING, ERROR)",
    )
