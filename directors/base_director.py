from abc import ABC, abstractmethod
from typing import Any
from dataclasses import dataclass

from tkscheduler import IterativeTask, Scheduler
from publisher import Publisher
from utils import add_termination_handler

DIRECTOR_CONTROL_RATE = 10  # control per sec


@dataclass
class ControlFeed:
    host: str
    manual: bool
    frame_shape: tuple
    publisher: Publisher

class BaseDirector(ABC):
    scheduler: Scheduler | None
    control_task: IterativeTask | None = None

    def __init__(self, tracker, connections, scheduler: Scheduler | None = None):
        self.tracker = tracker
        self.scheduler = scheduler
        self.control_feeds: dict[str, ControlFeed] = dict()
        for conn in connections.values():
            shape = conn.shape
            if shape is not None:
                self.control_feeds[conn.host] = ControlFeed(
                    host=conn.host, manual=conn.manual, frame_shape=shape, publisher=conn.publisher
                )
            else:
                print(
                    f"Warning: Connection {conn.host} has no frame shape set. "
                    "Make sure the video capture is properly initialized."
                )
        if self.control_feeds:
            self.start_auto_control()

    def add_control_feed(self, host: str, manual: bool, frame_shape: tuple, publisher: Publisher) -> None:
        self.control_feeds[host] = ControlFeed(
            host=host, manual=manual, frame_shape=frame_shape, publisher=publisher
        )
        if self.scheduler is not None and self.control_task is None:
            self.start_auto_control()

    def remove_control_feed(self, host: str) -> None:
        if host in self.control_feeds:
            del self.control_feeds[host]

    def update_control_feed(self, host: str, manual: bool) -> None:
        self.control_feeds[host].manual = manual

    # Processes the bounding box and sends commands
    @abstractmethod
    def process_frame(self, hostname: str, bounding_box: list, frame_shape: tuple, publisher: Publisher) -> Any:
        raise NotImplementedError("Subclasses must implement this method.")

    def track_obj(self) -> Any | None:
        bboxes = self.tracker.get_bboxes()
        for host, bbox in bboxes.items():
            if bbox is not None and len(bbox) > 0:
                if self.control_feeds[host].manual:
                    continue  # skip manual feeds
                return self.process_frame(host, bbox, self.control_feeds[host].frame_shape, self.control_feeds[host].publisher)
            else:
                print(
                    "[NOTICE]Boundary box not found. Make sure the object recognition is running."
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
