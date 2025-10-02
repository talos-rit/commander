from abc import ABC, abstractmethod

from config.tkscheduler import IterativeTask, Scheduler

from tracking.tracker import Tracker

DIRECTOR_CONTROL_RATE = 10  # control per sec


class BaseDirector(ABC):
    tracker: Tracker
    scheduler: Scheduler | None
    control_task: IterativeTask | None = None

    def __init__(self, tracker: Tracker, scheduler: Scheduler | None = None):
        self.tracker = tracker
        self.scheduler = scheduler

    # Processes the bounding box and sends commands
    @abstractmethod
    def process_frame(self, bounding_box: list, frame):
        raise NotImplementedError("Subclasses must implement this method.")

    def track_obj(self):
        # TODO: remove the usage of frames in this function because all it does is check the frame size
        bbox, frame = self.tracker.get_bbox(), self.tracker.get_frame()
        if bbox is not None:
            return self.process_frame(bbox, frame)

    def start_auto_control(self):
        if self.scheduler is not None:
            self.control_task = self.scheduler.set_interval(
                1000 / DIRECTOR_CONTROL_RATE, self.track_obj
            )
        else:
            raise NotImplementedError("No GUI mode not implemented")

    def stop_auto_control(self):
        if self.control_task is not None:
            self.control_task.cancel()
