import os
import yaml

# remember to add a .local version to .gitignore when creating new config directories

CAMERA_BASE_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "camera_config.yaml")
CAMERA_LOCAL_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "camera_config.local.yaml")

NETWORK_BASE_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "network_config.yaml")
NETWORK_LOCAL_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "network_config.local.yaml")

def load_a_config(base_path, local_path):
    def _load_yaml(path):
        if os.path.exists(path):
            with open(path, "r") as f:
                return yaml.safe_load(f) or {}
        return {}

    base_config = _load_yaml(base_path)
    local_config = _load_yaml(local_path)

    def merge_dicts(base, override):
        for k, v in override.items():
            if isinstance(v, dict) and isinstance(base.get(k), dict):
                merge_dicts(base[k], v)
            else:
                base[k] = v
        return base

    return merge_dicts(base_config, local_config)

CAMERA_CONFIG = load_a_config(CAMERA_BASE_CONFIG_PATH, CAMERA_LOCAL_CONFIG_PATH)
NETWORK_CONFIG = load_a_config(NETWORK_BASE_CONFIG_PATH, NETWORK_LOCAL_CONFIG_PATH)
