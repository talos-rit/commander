import os
import yaml
from glob import glob

from utils import get_file_path

DEFAULT_BASE_PATH = os.path.join(
    os.path.dirname(__file__), "config/default_config.yaml"
)
DEFAULT_LOCAL_PATH = os.path.join(
    os.path.dirname(__file__), "config/default_config.local.yaml"
)
if not os.path.exists(DEFAULT_LOCAL_PATH):
  DEFAULT_LOCAL_PATH = None

def add_config(socket_host: str, port: int):
    """
    Create a {socket_host}_config.yaml file based on default_config.yaml,
    replacing the socket_host and port variables with the passed in parameters.
    """
    base_dir = os.path.dirname(__file__)
    default_path = os.path.join(base_dir, "config/default_config.yaml")
    output_path = os.path.join(base_dir, f"config/{socket_host}_config.yaml")
    if os.path.exists(output_path):
        print(f"[WARNING] {output_path} already exists, not overwriting")
        return output_path

    # Load the default configuration
    with open(get_file_path(default_path), "r") as f:
        config_data = yaml.safe_load(f)

    # Update the first two fields if they exist
    keys = list(config_data.keys())
    if len(keys) >= 2:
        config_data[keys[0]] = socket_host
        config_data[keys[1]] = port
    else:
        raise ValueError("default_config.yaml has no socket_host and port fields")

    # Write the modified configuration
    with open(get_file_path(output_path), "w") as f:
        yaml.safe_dump(config_data, f, sort_keys=False)

    print(f"Created config/{socket_host}_config.yaml")
    return output_path

def find_config_pairs():
    """
    Searches the current directory for all *_config.yaml and *_config.local.yaml files.
    Returns a dictionary in the form:
        {
            "hostname": {
                "base": "/path/to/hostname_config.yaml",
                "local": "/path/to/hostname_config.local.yaml" or None
            },
            ...
        }
    - Excludes default_config.yaml and default_config.local.yaml.
    - If a local file has no matching base config, it is discarded with a warning.
    """
    base_dir = os.path.join(os.path.dirname(__file__), "config/")

    # Find all base and local configs
    base_configs = glob(os.path.join(base_dir, "*_config.yaml"))
    local_configs = glob(os.path.join(base_dir, "*_config.local.yaml"))

    # Filter out defaults
    base_configs = [f for f in base_configs if not f.endswith("default_config.yaml")]
    local_configs = [f for f in local_configs if not f.endswith("default_config.local.yaml")]

    # Maps of {hostname: file_path}
    base_map = {os.path.basename(f).replace("_config.yaml", ""): f for f in base_configs}
    local_map = {os.path.basename(f).replace("_config.local.yaml", ""): f for f in local_configs}

    config_pairs = {}

    # Pair up base with local configs via hostname
    for name, base_path in base_map.items():
        local_path = local_map.get(name)
        config_pairs[name] = {"base": base_path, "local": local_path}

    # Warn about unpaired local configs
    for name, local_path in local_map.items():
        if name not in base_map:
            print(f"[WARNING] Ignoring local config '{os.path.basename(local_path)}' (no matching base config found).")

    return config_pairs

def load_a_config(base_path, local_path = None):
    def _load_yaml(path):
        if os.path.exists(path):
            with open(get_file_path(path), "r") as f:
                return yaml.safe_load(f) or {}
        return {}

    base_config = _load_yaml(base_path)
    if local_path:
      local_config = _load_yaml(local_path)

      def merge_dicts(base, override):
          for k, v in override.items():
              if isinstance(v, dict) and isinstance(base.get(k), dict):
                  merge_dicts(base[k], v)
              else:
                  base[k] = v
          return base

      return merge_dicts(base_config, local_config)
    return base_config

def load_all_robot_configs():
    """
    Loads and merges all host configurations based on the map returned by find_config_pairs().
    Returns:
        {
            "socket_host": { merged config dict },
            ...
        }
    """
    pairs = find_config_pairs()
    robot_configs = {}

    for hostname, paths in pairs.items():
        base_path = paths["base"]
        local_path = paths["local"]

        try:
            config_data = load_a_config(base_path, local_path)
            robot_configs[hostname] = config_data
        except Exception as e:
            print(f"[WARNING] Failed to load config for '{hostname}': {e}")

    return robot_configs

ROBOT_CONFIGS = load_all_robot_configs()
DEFAULT_CONFIG = load_a_config(DEFAULT_BASE_PATH, DEFAULT_LOCAL_PATH)
