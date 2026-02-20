from typing import Optional

import yaml
from pydantic import ValidationError

from src.config import ROBOT_CONFIGS
from src.config.path import ROBOT_CONFIGS_PATH
from src.config.schema import ConnectionConfig


def add_config(connection_config: ConnectionConfig):
    """
    Add a new ConnectionConfig to the global ROBOT_CONFIGS dictionary.
    Args:
        connection_config: A validated ConnectionConfig object to add.
    """
    ROBOT_CONFIGS[connection_config.socket_host] = connection_config
    with open(ROBOT_CONFIGS_PATH, "a") as f:
        f.write("\n")
        yaml.dump(
            {connection_config.socket_host: connection_config.model_dump()},
            f,
        )


def validate_connection_config(
    socket_host: str,
    socket_port: int | str,
    camera_index: str,
    **kwargs,
) -> tuple[bool, Optional[ConnectionConfig], list[str]]:
    """
    Validate user input for a new connection (typically from UI dialog).
    Returns (is_valid, config, error_messages).

    Args:
        socket_host: IP/hostname
        socket_port: Port number (may be string from UI input)
        camera_index: Device index or URL (may be string)
        **kwargs: Additional config fields

    Returns:
        Tuple of (is_valid, ConnectionConfig or None, list of error messages)
    """
    errors = []
    valid_socket_port: int | None = None

    # Type coercion
    try:
        valid_socket_port = int(socket_port)
    except (ValueError, TypeError):
        errors.append(f"Port must be a valid integer, got '{socket_port}'")

    if not socket_host or not isinstance(socket_host, str):
        errors.append("Host must be a non-empty string")
    
    if socket_host in ROBOT_CONFIGS:
        errors.append(f"Robot configuration for host '{socket_host}' already exists")

    if errors or valid_socket_port is None:
        return False, None, errors

    # Try to create config
    try:
        config = ConnectionConfig(
            socket_host=socket_host,
            socket_port=valid_socket_port,
            camera_index=camera_index,
            **kwargs,
        )
        return True, config, []
    except ValidationError as e:
        # Pydantic validation error
        error_list = (
            e.errors() if hasattr(e, "errors") else [{"msg": str(e)}]
        )
        errors = [err.get("msg", str(err)) for err in error_list]
        return False, None, errors