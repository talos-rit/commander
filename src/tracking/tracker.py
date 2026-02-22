import threading
from enum import Enum
from multiprocessing import Process, Queue
from multiprocessing.managers import SharedMemoryManager
from queue import Empty

import cv2
import numpy as np
from loguru import logger

# TODO: Stop get rid of this import once AppSettings is implemented for non-connection specific settings/defaults
from src.config import DEFAULT_ROBOT_CONFIG
from src.scheduler import IterativeTask, Scheduler
from src.talos_app import ConnectionCollection
from src.tracking.detector import Detector, ObjectModel
from src.utils import (
    add_termination_handler,
    calculate_acceptable_box,
    calculate_center_bbox,
    remove_termination_handler,
)

from ..thread_scheduler import ThreadScheduler

SHARED_MEM_FRAME_NAME = "frame"
POLL_BBOX_CYCLE_INTERVAL_MS = 100  # 10 FPS


class BBOX_COLOR(Enum):
    RED = (255, 0, 0)
    GREEN = (0, 255, 0)
    BLUE = (0, 0, 255)
    CYAN = (0, 150, 150)


# Class for handling video feed and object detection model usage
class Tracker:
    speaker_bbox: tuple[int, int, int, int] | None = None
    max_fps = POLL_BBOX_CYCLE_INTERVAL_MS  # this will be set dynamically based on configuration see max_fps
    frame_delay: float = POLL_BBOX_CYCLE_INTERVAL_MS  # same as above
    bbox_delay: float = POLL_BBOX_CYCLE_INTERVAL_MS  # same as above
    model = None
    # captures: dict[str, VideoConnection] = dict()
    connections: ConnectionCollection
    frame_order: list[tuple[str, int]] = list()  # (host, frame x location)[]
    active_connection: str | None = None
    _scheduler: Scheduler
    _bboxes: dict[str, list] = dict()
    _bbox_lock: threading.Lock = threading.Lock()
    _frame_buf: np.ndarray
    _bbox_queue: Queue
    _detection_process: Process | None = None
    _term_handler_id: int | None = None
    _send_frame_task: IterativeTask | None = None
    _poll_bbox_task: IterativeTask | None = None
    _smm: SharedMemoryManager | None = None
    _bbox_success_count: int = 0
    _detector: Detector

    def __init__(
        self,
        connections: ConnectionCollection,
        scheduler: Scheduler = ThreadScheduler(),
        smm: SharedMemoryManager = SharedMemoryManager(),
        model=None,
    ):
        """
        Args:
            scheduler (Scheduler, optional): Scheduler for data pipeline tasks. Defaults to ThreadScheduler().
            smm (SharedMemoryManager, optional): Shared memory manager. Defaults to SharedMemoryManager().
            model (_type_, optional): Object detection model. Defaults to None.
        """
        self._scheduler = scheduler
        self.connections = connections
        self.model = model
        self.max_fps = DEFAULT_ROBOT_CONFIG.max_fps
        self.frame_delay = 1000 / DEFAULT_ROBOT_CONFIG.fps
        self.bbox_delay = 1000 / self.max_fps
        self._detector = Detector(model, connections, smm)
        logger.debug(f"Tracker initialized with max_fps: {self.max_fps}")

    def start_detection_process(self) -> None:
        if self._detector.is_running():
            return  # Already running
        logger.info("Starting detection process...")
        self._term_handler_id = add_termination_handler(self.stop)
        self.waiting_for_model = True
        logger.info("Waiting for model to load...")
        self._detector.start()
        logger.info(
            f"Detection process started. bbox delay:{self.bbox_delay}ms, frame delay:{self.frame_delay}ms"
        )
        self._send_frame_task = self._scheduler.set_interval(
            int(self.frame_delay), self.send_latest_frame
        )
        self._poll_bbox_task = self._scheduler.set_interval(
            int(self.bbox_delay), self.poll_bboxes
        )

    def poll_bboxes(self) -> None:
        try:
            bbox_map = self._detector.get_bboxes()
        except ValueError as e:
            logger.warning(f"Error getting bounding boxes: {e}")
            self.stop()
            return
        except Empty:
            if self.waiting_for_model:
                return
            if self._bbox_success_count < 1:
                self.decrease_bbox_frame_rate()
            self._bbox_success_count -= 1
            return
        if bbox_map is None:
            logger.warning("No bounding boxes detected.")
            return
        if self.waiting_for_model:
            logger.info("Model loaded, starting to poll bounding boxes.")
            self.waiting_for_model = False
        self._bbox_success_count += 1
        if self._bbox_success_count > 10:
            self.increase_bbox_frame_rate()
        with self._bbox_lock:
            self._bboxes = bbox_map

    def send_latest_frame(self) -> None:
        self._detector.send_input(self.waiting_for_model)

    def is_pipeline_running(self) -> bool:
        return self._send_frame_task is not None and self._poll_bbox_task is not None

    def stop_pipeline_tasks(self) -> bool:
        logger.debug("Stopping detection process...")
        if self._send_frame_task is not None:
            self._send_frame_task.cancel()
            self._send_frame_task = None
        if self._poll_bbox_task is not None:
            self._poll_bbox_task.cancel()
            self._poll_bbox_task = None
        with self._bbox_lock:
            self._bboxes = dict()
        logger.debug("Detection process stopped.")
        return True

    def stop(self) -> bool:
        if self._term_handler_id is not None:
            remove_termination_handler(self._term_handler_id)
            self._term_handler_id = None
        return self.stop_pipeline_tasks()

    def swap_model(self, new_model: ObjectModel.__class__ | None):
        """This will stop the current detection process and start a new process on the new model"""
        self._detector.set_model(new_model)
        if new_model is not None and not self._detector.is_running():
            self.start_detection_process()
        if new_model is None and self.is_pipeline_running():
            self.stop()

    def get_frame_shape(self, host):  # -> tuple[Any, ...] | None:
        """returns: (height, weight)"""
        if (conn := self.connections.get(host, None)) is not None:
            return conn.video_connection.shape

    def get_bboxes(self):
        with self._bbox_lock:
            return self._bboxes.copy()

    def draw_visuals(self, bboxes, frame):  # -> Any:
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

            # If speaker_bbox exists, draw line + distance
            if self.speaker_bbox is None:
                continue

            # Draw where the tracker is taking the color from - t-shirt area
            height = y2 - y1
            width = x2 - x1
            chest_start = y1 + int(height * 0.3)
            chest_end = y1 + int(height * 0.5)
            exclude_extra = x1 + int(width * 0.4)
            exclude_extra2 = x1 + int(width * 0.6)
            cv2.rectangle(
                frame,
                (exclude_extra, chest_start),
                (exclude_extra2, chest_end),
                BBOX_COLOR.CYAN.value,
                2,
            )

            # Red circle for speaker bbox
            cv2.circle(
                frame,
                calculate_center_bbox(self.speaker_bbox),
                10,
                BBOX_COLOR.RED.value,
                2,
            )
        return frame

    def get_frame(self, host: str | None = None):
        """This adds bounding box to the frame
        and return the latest frame of the active connection.
        """
        if (
            host is None
            or (conn := self.connections.get(host)) is None
            and (conn := self.connections.get_active()) is None
            or (cap := conn.video_connection) is None
        ):
            return logger.warning(f"No valid connection found for host: {host}")
        active_frame = cap.get_frame()
        bboxes_dict = self.get_bboxes()
        if (bboxes := bboxes_dict.get(host, None)) is not None:
            self.draw_visuals(bboxes, active_frame)
        return active_frame

    def increase_bbox_frame_rate(self) -> None:
        """Increase bbox polling rate by 10%, down to a minimum of max_fps in config."""
        if self._poll_bbox_task is None:
            return
        current_interval = self.bbox_delay
        new_interval = max(current_interval * 0.9, 1000.0 / self.max_fps)
        self.reschedule_bbox_task(new_interval)
        logger.debug(f"Increased bbox polling rate to {new_interval:.2f} ms.")

    def decrease_bbox_frame_rate(self) -> None:
        """Decrease bbox polling rate by 10%, up to a maximum of 1 FPS."""
        if self._poll_bbox_task is None:
            return
        new_interval = min(self.bbox_delay * 1.1, 1000.0)  # Maximum 1 FPS
        self.reschedule_bbox_task(new_interval)
        logger.debug(f"Decreased bbox polling rate to {new_interval:.2f} ms.")

    def reschedule_bbox_task(self, new_delay: float) -> None:
        """Reschedule the bbox polling task with the current bbox_delay."""
        if self._poll_bbox_task is None:
            return
        self.bbox_delay = new_delay
        self._poll_bbox_task.set_interval(int(self.bbox_delay))
