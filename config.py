import os
import yaml

from utils import get_file_path

CONFIG_PATH = get_file_path(os.path.join(
    os.path.dirname(__file__), "config/config.local.yaml"
))
DEFAULT_PATH = get_file_path(os.path.join(
    os.path.dirname(__file__), "config/default_config.yaml"
))
LOCAL_DEFAULT_PATH = get_file_path(os.path.join(
    os.path.dirname(__file__), "config/default_config.local.yaml"
))

def load_default_config():
    """
    Load the default configuration from config/default_config.yaml or
    config/default_config.local.yaml if it exists.
    """
    if os.path.exists(LOCAL_DEFAULT_PATH):
        with open(LOCAL_DEFAULT_PATH, "r") as f:
            default_config = yaml.safe_load(f)
    else:
        with open(DEFAULT_PATH, "r") as f:
            default_config = yaml.safe_load(f)
    return default_config

def load_config():
    """
    Load the configuration from config/config.local.yaml if it exists,
    otherwise load the default configuration from config/default_config.yaml.
    """
    config = dict()
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r") as f:
          config = yaml.safe_load(f)
    return config

def add_config(socket_host: str, port: int, camera_index: int):
    """
    WARNING: Changes global CONFIG variable to reflect the new configuration, therefore this variables MUST be re-imported after calling this function.

    Add a new local configuration to config/config.local.yaml based on config/default_config.yaml,
    or on config/default_config.local.yaml if it exists, updating the first two fields to socket_host and port.
    Creates config/config.local.yaml if it does not exist.
    Does not overwrite existing configurations.
    """
    base_dir = os.path.dirname(__file__)
    local_config_path = get_file_path(os.path.join(base_dir, "config/config.local.yaml"))

    # Load the default configuration
    local_config_data = load_default_config()

    # Update the first two fields if they exist
    keys = list(local_config_data.keys())
    if len(keys) >= 2:
        local_config_data[keys[0]] = socket_host
        local_config_data[keys[1]] = port
        local_config_data[keys[2]] = camera_index
    else:
        raise ValueError("default_config.yaml has no socket_host and port fields")

    # Load existing local configuration or create a new one\
    config = dict()
    if os.path.exists(local_config_path):
        with open(local_config_path, "r") as f:
            config = yaml.safe_load(f) or {}
    
    # Cancel if overwriting an existing configuration
    if config.get(socket_host):
        print(f"[WARNING] Configuration for '{socket_host}' already exists in config.local.yaml, not overwriting")
        return

    # Add the new configuration and write back to file
    config[socket_host] = local_config_data
    with open(local_config_path, "w") as f:
        yaml.safe_dump(config, f, sort_keys=False)

    # Update the global CONFIG variable
    global CONFIG
    CONFIG = load_config()

    return config

# Set global variables
CONFIG = load_config()
DEFAULT_CONFIG = load_default_config()
