import os

from utils import get_file_path

MODEL_ASSET_PATH = os.path.join(os.path.dirname(__file__), "assets")


def get_model_asset_path(file_name: str, _dir: str = MODEL_ASSET_PATH) -> str:
    return get_file_path(os.path.join(_dir, file_name))
