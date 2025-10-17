import os
import yaml

from utils import get_file_path

CONFIG_PATH = get_file_path(os.path.join(
    os.path.dirname(__file__), "config/config.local.yaml"
))

# Set default path allowing for local override
DEFAULT_PATH = get_file_path(os.path.join(
    os.path.dirname(__file__), "config/default_config.yaml"
))
local_default_path = get_file_path(os.path.join(
    os.path.dirname(__file__), "config/default_config.local.yaml"
))
if os.path.exists(local_default_path):
  DEFAULT_PATH = local_default_path

def load_config():
    """
    Load the configuration from config/config.local.yaml if it exists,
    otherwise load the default configuration from config/default_config.yaml.
    """
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r") as f:
          config = yaml.safe_load(f)
    else:
        print("[WARNING] no connection configurations found, loading default configuration with placeholder values")
        with open(DEFAULT_PATH, "r") as f:
            config = {}
            config["default_host"] = yaml.safe_load(f)
    return config

def add_config(socket_host: str, port: int):
    """
    WARNING: Changes global CONFIG variable to reflect the new configuration, therefore this variables MUST be re-imported after calling this function.

    Add a new local configuration to config/config.local.yaml based on config/default_config.yaml,
    or on config/default_config.local.yaml if it exists, updating the first two fields to socket_host and port.
    Creates config/config.local.yaml if it does not exist.
    Does not overwrite existing configurations.
    """
    base_dir = os.path.dirname(__file__)
    output_path = get_file_path(os.path.join(base_dir, "config/config.local.yaml"))

    # Load the default configuration
    with open(DEFAULT_PATH, "r") as f:
        config_data = yaml.safe_load(f)

    # Update the first two fields if they exist
    keys = list(config_data.keys())
    if len(keys) >= 2:
        config_data[keys[0]] = socket_host
        config_data[keys[1]] = port
    else:
        raise ValueError("default_config.yaml has no socket_host and port fields")

    # Load existing local configuration or create a new one
    if not os.path.exists(output_path):
        config = {}
    else:
        with open(output_path, "r") as f:
            config = yaml.safe_load(f) or {}

    # Ensure the root is a dictionary
    if not isinstance(config, dict):
        raise ValueError("config.local.yaml does not contain a dictionary at the root")
    
    # Cancel if overwriting an existing configuration
    if config.get(socket_host):
        print(f"[WARNING] Configuration for '{socket_host}' already exists in config.local.yaml, not overwriting")
        return

    # Add the new configuration and write back to file
    config[socket_host] = config_data
    with open(output_path, "w") as f:
        yaml.safe_dump(config, f, sort_keys=False)

    # Update the global CONFIG variable
    global CONFIG
    CONFIG = load_config()

CONFIG = load_config()
