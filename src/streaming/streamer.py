from enum import Enum

import cv2
from loguru import logger

from ..connection.connection import Connection, ConnectionCollection
from ..utils import calculate_acceptable_box, calculate_center_bbox
from .zoom import DigitalZoom


class BBOX_COLOR(Enum):
    RED = (255, 0, 0)
    GREEN = (0, 255, 0)
    BLUE = (0, 0, 255)
    CYAN = (0, 150, 150)
    FOCUS = (0, 200, 255)  # amber in OpenCV's BGR order


def draw_visuals(bboxes, frame, labels=None, highlight=None):  # -> Any:
    """
    Draws all the visuals we need on the frame. Rectangles around bounding boxes, circles in the middle, acceptable box for director, red dot for speaker.

    Parameters:
    - bounding_box - bounding boxes from capture frame
    - frame - frame to draw on
    - labels - optional text per box, such as the subject's tracker ID
    - highlight - index of the box to draw in the focus color
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

    for index, box in enumerate(bboxes):
        color = BBOX_COLOR.FOCUS.value if index == highlight else BBOX_COLOR.GREEN.value
        # Draw each bbox
        x1, y1, x2, y2 = map(int, box)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

        bbox_center_x, bbox_center_y = map(int, calculate_center_bbox(box))
        # Draw center of bounding box dot, this the value the commander is using
        cv2.circle(
            frame,
            (bbox_center_x, bbox_center_y),
            10,  # radius
            color,
            -1,  # fill the circle
        )
        if labels is not None and index < len(labels) and labels[index]:
            cv2.putText(
                frame,
                labels[index],
                (x1 + 4, max(16, y1 - 6)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                color,
                2,
            )
    return frame


class Streamer:
    draw_bboxes: bool

    def __init__(self, connections: ConnectionCollection, draw_bboxes: bool = False):
        self.connections = connections
        self.draw_bboxes = draw_bboxes
        self._zooms: dict[str, DigitalZoom] = {}

    def zoom(self, hostname: str) -> DigitalZoom:
        """The digital zoom applied to `hostname`'s frames."""
        return self._zooms.setdefault(hostname, DigitalZoom())

    def get_frame(self, hostname: str, annotate=None):
        """Latest frame for `hostname`, zoomed. `annotate` draws an overlay before the crop."""
        if hostname in self.connections:
            return self._render(hostname, self.connections[hostname], annotate)
        else:
            logger.error(f"Connection to {hostname} does not exist")
            return None

    def get_active_frame(self):
        active_conn = self.connections.get_active()
        if active_conn is not None:
            return self._render(active_conn.host, active_conn)
        else:
            logger.warning("No active connection found.")
            return None

    def _render(self, hostname: str, conn: Connection, annotate=None):
        video_conn = conn.video_connection
        frame = video_conn.get_latest_frame() if video_conn is not None else None
        if frame is None:
            return None
        observations = conn.get_observations() or []
        target = conn.focus_track_id
        if self.draw_bboxes and (bboxes := conn.get_bboxes()) is not None:
            labels = None
            highlight = None
            if len(observations) == len(bboxes):
                ids = [o.local_track_id for o in observations]
                labels = [f"#{i}" if i is not None else None for i in ids]
                if target is not None and target in ids:
                    highlight = ids.index(target)
            frame = draw_visuals(bboxes, frame.copy(), labels, highlight)
        if annotate is not None:
            frame = annotate(frame)
        return self.zoom(hostname).apply(frame, observations, target)
