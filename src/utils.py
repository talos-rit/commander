import signal

from loguru import logger

import src.config as config


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

    acceptable_box_percent = (
        acceptable_box_percent or config.DEFAULT_ROBOT_CONFIG.acceptable_box_percent
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


def id_generator():
    """Id generator for handlers."""
    current_id = 0
    while True:
        yield current_id
        current_id += 1


class TerminationHandler:
    id: int | None = None

    def __init__(self, func) -> None:
        self.func = func

    def __call__(self, *args, **kwds):
        return self.func(*args, **kwds)


TERMINATION_HANDLERS: list[TerminationHandler] | None = None
ID_GEN = id_generator()


def _ensure_termination_handlers() -> list[TerminationHandler]:
    global TERMINATION_HANDLERS
    if TERMINATION_HANDLERS is None:
        start_termination_guard()
    if TERMINATION_HANDLERS is None:
        TERMINATION_HANDLERS = []
    return TERMINATION_HANDLERS


def start_termination_guard():
    logger.debug("Setting up cleanup handlers")
    global TERMINATION_HANDLERS
    TERMINATION_HANDLERS = []
    signal.signal(signal.SIGINT, terminate)


def add_termination_handler(call):
    global TERMINATION_HANDLERS, ID_GEN
    handlers = _ensure_termination_handlers()
    handler = TerminationHandler(call)
    handler.id = next(ID_GEN)
    handlers.append(handler)
    return handler.id


def terminate(signum, frame):
    global TERMINATION_HANDLERS
    handlers = _ensure_termination_handlers()
    logger.debug(f"\nSignal {signum} received! Executing handler.")
    logger.debug(f"Performing cleanup or specific action... {len(handlers)}")

    while len(handlers) > 0:
        handler = handlers.pop()
        handler()
    logger.info("Finished clean up")


def remove_termination_handler(id: int):
    global TERMINATION_HANDLERS
    handlers = _ensure_termination_handlers()
    TERMINATION_HANDLERS = [h for h in handlers if h.id != id]
