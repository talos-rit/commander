import os
from src.utils import get_file_path


CONNECTIONS_PATH = get_file_path(
    os.path.join(os.path.dirname(__file__), "../../config/connections.local.yaml")
)
DEFAULT_PATH = get_file_path(
    os.path.join(os.path.dirname(__file__), "../../config/default_config.yaml")
)
LOCAL_DEFAULT_PATH = get_file_path(
    os.path.join(os.path.dirname(__file__), "../../config/default_config.local.yaml")
)