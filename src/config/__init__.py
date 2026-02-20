# TODO: Stop exposing DEFAULT_ROBOT_CONFIG once AppSettings is implemented for non-connection specific settings/defaults
from src.config.load import DEFAULT_ROBOT_CONFIG, load_robot_config
from src.config.schema import ConnectionConfig

ROBOT_CONFIGS = load_robot_config()


def __getattr__(name):
    """Lazy load add_config and validate_connection_config to avoid circular imports."""
    import src.config.add as editor
    
    if name == "editor":
        return editor
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = ["ROBOT_CONFIGS", "ConnectionConfig", "DEFAULT_ROBOT_CONFIG"]