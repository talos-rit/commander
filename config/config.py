import os
import yaml

DEFAULT_BASE_PATH = os.path.join(
    os.path.dirname(__file__), "default_config.yaml"
)
DEFAULT_LOCAL_PATH = os.path.join(
    os.path.dirname(__file__), "default_config.local.yaml"
)

def add_config(socket_host: str, port: int):
    """
    Create a {socket_host}_config.yaml file based on default_config.yaml,
    replacing the socket_host and port variables with the passed in parameters.
    """
    base_dir = os.path.dirname(__file__)
    default_path = os.path.join(base_dir, "default_config.yaml")
    output_path = os.path.join(base_dir, f"{socket_host}_config.yaml")

    # Load the default configuration
    with open(default_path, "r") as f:
        config_data = yaml.safe_load(f)

    # Update the first two fields if they exist
    keys = list(config_data.keys())
    if len(keys) >= 2:
        config_data[keys[0]] = socket_host
        config_data[keys[1]] = port
    else:
        raise ValueError("default_config.yaml has no socket_host and port fields")

    # Write the modified configuration
    with open(output_path, "w") as f:
        yaml.safe_dump(config_data, f, sort_keys=False)

    print(f"Created {output_path}")
    return output_path

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

#testing

# if __name__ == "__main__":
#     add_config("testhost", 8080)
