from abc import ABC, abstractmethod

from tkscheduler import IterativeTask, Scheduler
from tracking.tracker import Tracker
from utils import add_termination_handler

DIRECTOR_CONTROL_RATE = 10  # control per sec


class BaseDirector(ABC):
    tracker: Tracker
    scheduler: Scheduler | None
    control_task: IterativeTask | None = None

    def __init__(self, tracker: Tracker, scheduler: Scheduler | None = None):
        self.tracker = tracker
        self.scheduler = scheduler
        self.frame_shape = self.tracker.get_frame_shape()

    # Processes the bounding box and sends commands
    @abstractmethod
    def process_frame(self, bounding_box: list, frame_shape):
        raise NotImplementedError("Subclasses must implement this method.")

    def track_obj(self):
        bbox = self.tracker.get_bbox()
        if bbox is not None:
            return self.process_frame(bbox, self.frame_shape)

    def start_auto_control(self):
        if self.scheduler is not None:
            self.control_task = self.scheduler.set_interval(
                1000 / DIRECTOR_CONTROL_RATE, self.track_obj
            )
            add_termination_handler(self.stop_auto_control)
        else:
            raise NotImplementedError("No GUI mode not implemented")

    def stop_auto_control(self):
        if self.control_task is not None:
            self.control_task.cancel()
