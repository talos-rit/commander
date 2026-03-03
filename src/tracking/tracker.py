from enum import Enum
from multiprocessing.managers import SharedMemoryManager
from queue import Empty
from typing import Any

from loguru import logger

from src.scheduler import IterativeTask, Scheduler
from src.talos_app import ConnectionCollection
from src.tracking.detector import DetectionWaitingForModel, Detector, ObjectModel
from src.utils import (
    add_termination_handler,
    remove_termination_handler,
)

from ..config.load import APP_SETTINGS
from ..connection.connection import ConnectionCollectionEvent
from ..thread_scheduler import ThreadScheduler

SHARED_MEM_FRAME_NAME = "frame"


class BBOX_COLOR(Enum):
    RED = (255, 0, 0)
    GREEN = (0, 255, 0)
    BLUE = (0, 0, 255)
    CYAN = (0, 150, 150)


# Class for handling video feed and object detection model usage
class Tracker:
    # this will be set dynamically based on configuration see max_fps
    max_fps: int
    frame_delay: float  # same as above
    bbox_delay: float  # same as above
    connections: ConnectionCollection
    _scheduler: Scheduler
    _term_handler_id: int | None = None
    _send_frame_task: IterativeTask | None = None
    _poll_bbox_task: IterativeTask | None = None
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
        self.max_fps = APP_SETTINGS.bbox_max_fps
        self.frame_delay = 1000 / APP_SETTINGS.frame_process_fps
        self.bbox_delay = 1000 / self.max_fps
        self._detector = Detector(model, connections, smm)
        logger.debug(f"Tracker initialized with max_fps: {self.max_fps}")

    def on_connection_update(self, event: ConnectionCollectionEvent, *_: Any):
        if event == ConnectionCollectionEvent.REMOVED and len(self.connections) == 0:
            logger.debug("No more connections available, stopping detection process...")
            self.stop()

    def start_detection_process(self) -> None:
        if self._detector.is_running():
            return  # Already running
        logger.info("Starting detection process...")
        self._detector.start()
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
        try:
            self._detector.get_bboxes()
        except DetectionWaitingForModel:
            return
        except ValueError as e:
            logger.warning(f"Error getting bounding boxes: {e}")
            self.stop()
            return
        except Empty:
            if self._bbox_success_count < 1:
                self.decrease_bbox_frame_rate()
            self._bbox_success_count -= 1
            return
        self._bbox_success_count += 1
        if self._bbox_success_count > 10:
            self.increase_bbox_frame_rate()

    def send_latest_frame(self) -> None:
        self._detector.send_input()

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

    def increase_bbox_frame_rate(self) -> None:
        """Increase bbox polling rate by 10%, down to a minimum of max_fps in config."""
        if self._poll_bbox_task is None:
            return
        current_interval = self.bbox_delay
        new_interval = max(current_interval * 0.9, 1000.0 / self.max_fps)
        self.reschedule_bbox_task(new_interval)
        if new_interval <= 1000.0 / self.max_fps:
            logger.warning(
                f"Bbox polling rate is at maximum (max_fps={self.max_fps}). Consider upgrading your model or increasing max_fps in settings."
            )

    def decrease_bbox_frame_rate(self) -> None:
        """Decrease bbox polling rate by 10%, up to a maximum of 1 FPS."""
        if self._poll_bbox_task is None:
            return
        new_interval = min(self.bbox_delay * 1.1, 1000.0)  # Maximum 1 FPS
        self.reschedule_bbox_task(new_interval)
        if new_interval >= 900.0:
            logger.warning(
                "Resource seems to be struggling. Consider using a smaller model."
            )

    def reschedule_bbox_task(self, new_delay: float) -> None:
        """Reschedule the bbox polling task with the current bbox_delay."""
        if self._poll_bbox_task is None:
            return
        self.bbox_delay = new_delay
        self._poll_bbox_task.set_interval(int(self.bbox_delay))

    def get_output_fps(self) -> float:
        """Get the current frame rate of the bbox polling task."""
        if self._poll_bbox_task is None:
            return 0.0
        return 1000.0 / self.bbox_delay

    def get_input_fps(self) -> float:
        """Get the current frame rate of the frame sending task."""
        if self._send_frame_task is None:
            return 0.0
        return 1000.0 / self.frame_delay
