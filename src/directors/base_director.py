from abc import ABC, abstractmethod
from typing import Any

from src.tkscheduler import IterativeTask, Scheduler
from src.utils import add_termination_handler

DIRECTOR_CONTROL_RATE = 10  # control per sec


class BaseDirector(ABC):
    scheduler: Scheduler | None
    control_task: IterativeTask | None = None

    def __init__(self, tracker, scheduler: Scheduler | None = None):
        self.tracker = tracker
        self.scheduler = scheduler
        self.frame_shape = self.tracker.get_frame_shape()

    # Processes the bounding box and sends commands
    @abstractmethod
    def process_frame(self, bounding_box: list, frame_shape) -> Any:
        raise NotImplementedError("Subclasses must implement this method.")

    def track_obj(self) -> Any | None:
        bbox = self.tracker.get_bbox()
        if bbox is not None and len(bbox) > 0:
            return self.process_frame(bbox, self.frame_shape)
        else:
            print(
                "Boundary box not found. Make sure the object recognition is running."
            )

    def start_auto_control(self) -> None:
        if self.scheduler is not None:
            self.control_task = self.scheduler.set_interval(
                1000 / DIRECTOR_CONTROL_RATE, self.track_obj
            )
            add_termination_handler(self.stop_auto_control)
        else:
            # TODO: implement this
            raise NotImplementedError("No GUI mode not implemented")

    def stop_auto_control(self) -> None:
        if self.control_task is not None:
            self.control_task.cancel()
