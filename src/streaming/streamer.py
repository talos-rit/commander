from enum import Enum

import cv2
from loguru import logger

from ..connection.connection import ConnectionCollection
from ..utils import calculate_acceptable_box, calculate_center_bbox


class BBOX_COLOR(Enum):
    RED = (255, 0, 0)
    GREEN = (0, 255, 0)
    BLUE = (0, 0, 255)
    CYAN = (0, 150, 150)


def draw_visuals(bboxes, frame):  # -> Any:
    """
    Draws all the visuals we need on the frame. Rectangles around bounding boxes, circles in the middle, acceptable box for director, red dot for speaker.

    Parameters:
    - bounding_box - bounding boxes from capture frame
    - frame - frame to draw on
    """
    # Draw the acceptable box
    frame_height = frame.shape[0]
    frame_width = frame.shape[1]
    (
        acceptable_box_left,
        acceptable_box_top,
        acceptable_box_right,
        acceptable_box_bottom,
    ) = calculate_acceptable_box(frame_width, frame_height)
    cv2.rectangle(
        frame,
        (acceptable_box_left, acceptable_box_top),
        (acceptable_box_right, acceptable_box_bottom),
        BBOX_COLOR.BLUE.value,
        2,  # thickness
    )

    for box in bboxes:
        # Draw each bbox
        x1, y1, x2, y2 = box
        cv2.rectangle(frame, (x1, y1), (x2, y2), BBOX_COLOR.GREEN.value, 2)

        bbox_center_x, bbox_center_y = calculate_center_bbox(box)
        # Draw center of bounding box dot, this the value the commander is using
        cv2.circle(
            frame,
            (bbox_center_x, bbox_center_y),
            10,  # radius
            BBOX_COLOR.GREEN.value,
            -1,  # fill the circle
        )
    return frame


class Streamer:
    draw_bboxes: bool

    def __init__(self, connections: ConnectionCollection, draw_bboxes: bool = False):
        self.connections = connections
        self.draw_bboxes = draw_bboxes

    def get_frame(self, hostname: str):
        if hostname in self.connections:
            conn = self.connections[hostname]
            frame = conn.video_connection.get_frame()
            if frame is not None and self.draw_bboxes:
                bboxes = conn.get_bboxes()
                frame = draw_visuals(bboxes, frame)
            return frame
        else:
            logger.error(f"Connection to {hostname} does not exist")
            return None

    def get_active_frame(self):
        active_conn = self.connections.get_active()
        if active_conn is not None:
            frame = active_conn.video_connection.get_frame()
            if (
                frame is not None
                and self.draw_bboxes
                and (bboxes := active_conn.get_bboxes()) is not None
            ):
                frame = draw_visuals(bboxes, frame)
            return frame
        else:
            logger.warning("No active connection found.")
            return None
