from os import path

from utils import get_file_path

ASSET_DIRPATH = path.dirname(path.abspath(__file__))


def join_paths(*paths: str) -> str:
    return get_file_path(path.join(ASSET_DIRPATH, *paths))
