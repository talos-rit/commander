import os.path as path
import sys


def get_file_path(relative_path: str) -> str:
    """
    Get the absolute file path for a given relative path. This method is necessary
    to ensure the program works when compiled with PyInstaller.

    Args:
        relative_path (str): The relative path to the file.

    Returns:
        str: The absolute file path if the program is compiled with PyInstaller, otherwise the relative path.
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return path.join(sys._MEIPASS, relative_path)
    return relative_path
