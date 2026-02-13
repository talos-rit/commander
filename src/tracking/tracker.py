import threading
from abc import ABC, abstractmethod
from enum import Enum
from multiprocessing import Event, Process, Queue, shared_memory
from multiprocessing.managers import SharedMemoryManager
from queue import Empty, Full

import cv2
import numpy as np
from loguru import logger

# TODO: Stop get rid of this import once AppSettings is implemented for non-connection specific settings/defaults
from src.config import DEFAULT_ROBOT_CONFIG
from src.connection.connection import VideoConnection
from src.scheduler import IterativeTask, Scheduler
from src.utils import (
    add_termination_handler,
    calculate_acceptable_box,
    calculate_center_bbox,
    remove_termination_handler,
)

from ..logger import configure_logger
from ..thread_scheduler import ThreadScheduler

SHARED_MEM_FRAME_NAME = "frame"
POLL_BBOX_CYCLE_INTERVAL_MS = 100  # 10 FPS


class BBOX_COLOR(Enum):
    RED = (255, 0, 0)
    GREEN = (0, 255, 0)
    BLUE = (0, 0, 255)
    CYAN = (0, 150, 150)


class ObjectModel(ABC):
    """
    This is a model class where it can handle turning image frame into bounding box
    The reason why this is separated is due to the fact that this will be running in a separate process.
    """

    # Capture a frame from the source
    @abstractmethod
    def detect_person(self, frame) -> list:  # bboxes
        raise NotImplementedError()


def _detect_person_worker(
    model_class,
    bbox_queue: Queue,
    stopper,
    frame_ready_event,
    frame_mem: shared_memory.SharedMemory,
    frame_shape,
    frame_dtype,
) -> None:
    configure_logger(process_name="detection_process", remove_existing=True)
    logger.info("Detection process started.")
    if model_class is None:
        logger.error("Model was not found please pass a model into Tracker to run.")
        return
    frame = np.ndarray(frame_shape, dtype=frame_dtype, buffer=frame_mem.buf)
    model: ObjectModel = model_class()
    try:
        while not stopper.is_set():
            logger.debug("Waiting for new frame...")
            frame_ready_event.wait()
            # Not clear immediately to make a copy here safely
            bboxes = model.detect_person(frame=np.copy(frame))
            frame_ready_event.clear()
            try:
                bbox_queue.put_nowait(bboxes)
            except Full:
                logger.warning("bbox_queue is full, skipping frame")
    except KeyboardInterrupt:
        logger.info("Detection process received KeyboardInterrupt, exiting.")
        pass
    except ValueError:
        logger.error("bbox_queue closed")


# Class for handling video feed and object detection model usage
class Tracker:
    speaker_bbox: tuple[int, int, int, int] | None = None
    max_fps = POLL_BBOX_CYCLE_INTERVAL_MS  # this will be set dynamically based on configuration see max_fps
    frame_delay: float = POLL_BBOX_CYCLE_INTERVAL_MS  # same as above
    bbox_delay: float = POLL_BBOX_CYCLE_INTERVAL_MS  # same as above
    model = None
    captures: dict[str, VideoConnection] = dict()
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

    def __init__(
        self,
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
        self.model = model
        self._smm = smm
        self.max_fps = DEFAULT_ROBOT_CONFIG.max_fps
        self.frame_delay = 1000 / DEFAULT_ROBOT_CONFIG.fps
        self.bbox_delay = 1000 / self.max_fps
        self._smm.start()
        logger.debug(f"Tracker initialized with max_fps: {self.max_fps}")

    def add_capture(self, host: str, camera: str | int) -> VideoConnection:
        """Adds a new video capture for a given host.
        If the detection process is running this will restart it.
        Parameters:
        - host: unique identifier for the video source
        - camera: video source (file path or camera index)
        Returns:
        - VideoConnection: new video connection object
        """
        restart = False
        if self._detection_process is not None:
            restart = True
            self.stop_detection_process()
        elif self.model is not None:
            restart = True
        conn = VideoConnection(src=camera)
        self.captures[host] = conn
        self.frame_order.append((host, 0))
        if restart:
            self.start_detection_process()
        return conn

    def remove_capture(self, host: str | None = None) -> None:
        """Releases video capture for a given host if not all video capture is closed."""
        if host is None:
            for cap in self.captures.values():
                cap.close()
            self.captures = dict()
            self.frame_order = list()
            self.stop_detection_process()
            return
        if host in self.captures:
            self.captures[host].close()
            del self.captures[host]
        self.frame_order = [fo for fo in self.frame_order if fo[0] != host]
        if not self.captures:
            self.stop_detection_process()

    def start_detection_process(self) -> None:
        if self._detection_process is not None:
            return  # Already running
        assert self._smm is not None
        logger.info("Starting detection process...")
        total_shape = self.get_total_frame_shape()
        total_nbytes = self.get_nbytes_from_total_shape(total_shape)

        self.model_stopper = Event()
        self.frame_ready_event = Event()
        # idk why but gc keeps deleting shared memory without me holding reference via "self."
        self._frame_memory = self._smm.SharedMemory(size=total_nbytes)
        self._frame_buf = np.ndarray(total_shape, np.uint8, self._frame_memory.buf)
        # we only care about the latest bbox but I prefer to have more than 1 allocated size
        self._bbox_queue = Queue(maxsize=2)
        self._detection_process = Process(
            target=_detect_person_worker,
            args=(
                self.model,
                self._bbox_queue,
                self.model_stopper,
                self.frame_ready_event,
                self._frame_memory,
                total_shape,
                np.uint8,
            ),
            daemon=True,
        )
        self._detection_process.start()
        self._term_handler_id = add_termination_handler(self.stop)
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
        logger.debug("Polling bounding boxes from detection process")
        raw_bboxes: None | list[tuple[int, int, int, int]] = None

        try:
            raw_bboxes = self._bbox_queue.get(block=False)
        except ValueError:
            return
        except Empty:
            if self._bbox_success_count < 1:
                logger.debug(f"Reducing poll rate. Counts: {self._bbox_success_count}")
                self.decrease_bbox_frame_rate()
            self._bbox_success_count -= 1
            return
        if raw_bboxes is None:
            logger.info("No bounding boxes detected.")
            return
        self._bbox_success_count += 1
        if self._bbox_success_count > 10:
            logger.debug(f"Increasing poll rate. Counts: {self._bbox_success_count}")
            self.increase_bbox_frame_rate()

        bboxes_by_host: dict = {host: [] for host, _ in self.frame_order}

        if 1 == len(self.frame_order):
            (host, _) = self.frame_order[0]
            with self._bbox_lock:
                self._bboxes = {host: raw_bboxes}
            return

        for x1, y1, x2, y2 in raw_bboxes:
            cx = (x1 + x2) // 2

            for index, (host, dx) in enumerate(self.frame_order):
                if index == len(self.frame_order) - 1:
                    bboxes_by_host[host].append(
                        [max(0, x1 - dx), y1, max(0, x2 - dx), y2]
                    )
                    continue
                (_, dx_next) = self.frame_order[index + 1]
                if cx >= dx and cx < dx_next:
                    bboxes_by_host[host].append(
                        [max(0, x1 - dx), y1, max(0, x2 - dx), y2]
                    )

        with self._bbox_lock:
            self._bboxes = bboxes_by_host
            logger.info(f"Updated bounding boxes: {self._bboxes}")

    def get_total_frame_shape(self):
        """
        Merges all of the frames side by side in a predictive manner.
        """
        total_width = 0
        max_height = 0
        self.frame_order = list()
        for host, vid in self.captures.items():
            if (shape := vid.shape) is None:
                continue
            max_height = max(max_height, shape[0])
            self.frame_order.append((host, total_width))
            total_width = total_width + shape[1]
        return (max_height, total_width, 3)

    def get_nbytes_from_total_shape(self, shape):
        """Given total frame shape, calculate nbytes for shared memory.

        Accepts shape in either (height, width) or (height, width, channels).
        Assumes 8-bit per channel (np.uint8) which is standard for OpenCV frames.
        """
        if shape is None:
            return 0
        if len(shape) == 2:
            height, width = shape
            channels = 3
        elif len(shape) == 3:
            height, width, channels = shape
        else:
            raise ValueError(f"Unsupported shape length: {len(shape)}")

        try:
            h, w, c = int(height), int(width), int(channels)
        except (TypeError, ValueError):
            raise ValueError("Shape elements must be integers")

        return h * w * c * np.dtype(np.uint8).itemsize

    def send_latest_frame(self) -> None:
        if self.frame_ready_event.is_set():
            logger.debug("Frame ready event already set, skipping frame update")
            return
        logger.debug("Sending latest frame to detection process")
        if 1 == len(self.frame_order):
            (host, _) = self.frame_order[0]
            self.new_frame = self.captures[host].get_frame()
            if self.new_frame is not None and not self.frame_ready_event.is_set():
                np.copyto(self._frame_buf, self.new_frame)
                self.frame_ready_event.set()
            return

        frames = [self.captures[host].get_frame() for host, _ in self.frame_order]
        frames = [f for f in frames if f is not None]
        if len(frames) == 0:
            logger.warning("No frames available to update frame buffer.")
            return
        # Compare heights of frames and padd the bottom to the smaller ones to match the largest height
        max_height = max(frame.shape[0] for frame in frames)
        resized_frames = [
            frame
            if frame.shape[0] == max_height
            else np.pad(
                frame,
                ((0, max_height - frame.shape[0]), (0, 0), (0, 0)),
                mode="constant",
                constant_values=0,
            )
            for frame in frames
        ]
        hstack = np.hstack(resized_frames)
        np.copyto(self._frame_buf, hstack)
        self.frame_ready_event.set()

    def stop_detection_process(self) -> bool:
        """Returns true if process properly closed"""
        if self._detection_process is None:
            return True
        assert self._smm is not None
        if self._send_frame_task is not None:
            self._send_frame_task.cancel()
            self._send_frame_task = None
        if self._poll_bbox_task is not None:
            self._poll_bbox_task.cancel()
            self._poll_bbox_task = None
        with self._bbox_lock:
            self._bboxes = dict()
        if self._detection_process is not None:
            try:
                self.frame_ready_event.clear()
                self.model_stopper.set()
                self._detection_process.join()
                self._bbox_queue.close()
                self._bbox_queue.join_thread()
                self.model_stopper.clear()
            except Exception as e:
                logger.error(f"Exception occured: {e}")
                return False
            self._detection_process = None
            logger.info("Detection process stopped.")
        return True

    def get_frame_shape(self, host):  # -> tuple[Any, ...] | None:
        """returns: (height, weight)"""
        if (conn := self.captures.get(host, None)) is not None:
            return conn.shape

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
            and (host := self.active_connection) is None
            or (cap := self.captures.get(host, None)) is None
        ):
            return
        active_frame = cap.get_frame()
        bboxes_dict = self.get_bboxes()
        if (bboxes := bboxes_dict.get(host, None)) is not None:
            self.draw_visuals(bboxes, active_frame)
        return active_frame

    def set_active_connection(self, connection: str | None) -> None:
        self.active_connection = connection

    def stop(self) -> bool:
        if self._term_handler_id is not None:
            remove_termination_handler(self._term_handler_id)
            self._term_handler_id = None
        self.remove_capture()
        for _ in range(6):
            if self.stop_detection_process():
                self._smm.shutdown() if self._smm is not None else None
                self._smm = None
                return True
        return False

    def swap_model(self, new_model) -> None:
        """This will stop the current detection process and start a new process on the new model"""
        if not self.stop_detection_process():
            logger.error("Failed to stop detection model")
            return
        self.model = new_model
        if self.captures is not None and self.model is not None:
            # do not start detection process if there are no captures, or if model is None
            self.start_detection_process()

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