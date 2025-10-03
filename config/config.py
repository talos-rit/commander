import os
import yaml

DEFAULT_BASE_PATH = os.path.join(
    os.path.dirname(__file__), "config.yaml"
)
DEFAULT_LOCAL_PATH = os.path.join(
    os.path.dirname(__file__), "config.local.yaml"
)


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

DEFAULT_CONFIG = load_a_config(DEFAULT_BASE_PATH, DEFAULT_LOCAL_PATH)
