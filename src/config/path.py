import os
from src.utils import get_file_path


CONFIG_PATH = get_file_path(
    os.path.join(os.path.dirname(__file__), "../../config/config.local.yaml")
)
DEFAULT_PATH = get_file_path(
    os.path.join(os.path.dirname(__file__), "../../config/default_config.yaml")
)
LOCAL_DEFAULT_PATH = get_file_path(
    os.path.join(os.path.dirname(__file__), "../../config/default_config.local.yaml")
)