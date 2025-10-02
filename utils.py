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


def calculate_acceptable_box(
    frame_width, frame_height, acceptable_box_percent: float | None = None
):
    """
    Get the values from the config to create the acceptable box of where the speaker can be without sending movements.
    Used in the drawing.
    Parameters:
    - bbox_width
    - frame_height
    """
    if acceptable_box_percent is None:
        from config import CAMERA_CONFIG

        acceptable_box_percent = (
            acceptable_box_percent or CAMERA_CONFIG["acceptable_box_percent"]
        )

    # Use the frame height and width to calculate an acceptable box
    # Calculate the frame's center
    frame_center_x = frame_width // 2
    frame_center_y = frame_height // 2

    # Define the acceptable box (50% of width and height around the center)
    acceptable_width = int(frame_width * acceptable_box_percent)
    acceptable_height = int(frame_height * acceptable_box_percent)

    acceptable_box_left = frame_center_x - (acceptable_width // 2)
    acceptable_box_top = frame_center_y - (acceptable_height // 2)
    acceptable_box_right = frame_center_x + (acceptable_width // 2)
    acceptable_box_bottom = frame_center_y + (acceptable_height // 2)
    return (
        acceptable_box_left,
        acceptable_box_top,
        acceptable_box_right,
        acceptable_box_bottom,
    )


def calculate_center_box(x, y, w, h):
    """
    Simple method to calculate the center of a bounding box
    """
    return (x + w) // 2, (y + h) // 2


def calculate_center_bbox(bbox: tuple[int, int, int, int]):
    return calculate_center_box(*bbox)


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
