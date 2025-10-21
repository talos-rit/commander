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
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r") as f:
          config = yaml.safe_load(f)
    else:
        #TODO: change to default config with placeholder values once add_config can be easily used
        print("[WARNING] no connection configurations found, adding known dev configuration")
        add_config("unctalos.student.rit.edu", 61616)
        with open(CONFIG_PATH, "r") as f:
          config = yaml.safe_load(f)
        # print("[WARNING] no connection configurations found, loading default configuration with placeholder values")
        # config = {}
        # config["default_host"] = load_default_config()
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
    config_data = load_default_config()

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

    return config

# Set global variables
CONFIG = load_config()
DEFAULT_CONFIG = load_default_config()
