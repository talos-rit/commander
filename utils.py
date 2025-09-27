import os.path as path
import signal
import sys
import threading

import yaml


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
        return path.join(sys._MEIPASS, relative_path)  # pyright: ignore[reportAttributeAccessIssue]
    return relative_path


def load_config(config_path):
    with open(config_path, "r") as file:
        return yaml.safe_load(file)


TERMINATION_HANDLERS = []
TERMINATION_THREAD_LOCK = threading.Lock()


def add_termination_handler(handler):
    global TERMINATION_HANDLERS
    with TERMINATION_THREAD_LOCK:
        TERMINATION_HANDLERS.append(handler)


def terminate(signum, frame):
    global TERMINATION_HANDLERS
    print(f"\nSignal {signum} received! Executing handler.")
    print("Performing cleanup or specific action...")

    for handler in TERMINATION_HANDLERS:
        handler()

    sys.exit(0)


signal.signal(signal.SIGINT, terminate)
