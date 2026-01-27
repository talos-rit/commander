from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from src.connection.connection import Connection
from src.connection.publisher import Publisher
from src.scheduler import IterativeTask, Scheduler
from src.utils import add_termination_handler, remove_termination_handler

DIRECTOR_CONTROL_RATE = 10  # control per sec


@dataclass
class ControlFeed:
    host: str
    manual: bool
    frame_shape: tuple
    publisher: Publisher
    tracking_priority: str


class BaseDirector(ABC):
    scheduler: Scheduler | None
    control_task: IterativeTask | None = None
    _term: int | None = None

    def __init__(
        self,
        tracker,
        connections: dict[str, Connection],
        scheduler: Scheduler | None = None,
    ):
        self.tracker = tracker
        self.scheduler = scheduler
        self.control_feeds: dict[str, ControlFeed] = dict()
        for conn in connections.values():
            shape = conn.video_connection.shape
            if shape is not None:
                self.control_feeds[conn.host] = ControlFeed(
                    host=conn.host,
                    manual=conn.is_manual,
                    frame_shape=shape,
                    publisher=conn.publisher,
                    tracking_priority=conn.tracking_priority,
                )
            else:
                print(
                    f"Warning: Connection {conn.host} has no frame shape set. "
                    "Make sure the video capture is properly initialized."
                )
        if self.control_feeds:
            self.start_auto_control()

    def add_control_feed(
        self, host: str, manual: bool, frame_shape: tuple, publisher: Publisher, tracking_priority: str
    ) -> ControlFeed:
        cf = ControlFeed(
            host=host, manual=manual, frame_shape=frame_shape, publisher=publisher, tracking_priority=tracking_priority
        )
        self.control_feeds[host] = cf
        if self.scheduler is not None and self.control_task is None:
            self.start_auto_control()
        return cf

    def remove_control_feed(self, host: str) -> None:
        if host in self.control_feeds:
            del self.control_feeds[host]
        if not self.control_feeds:
            self.stop_auto_control()

    def update_control_feed(self, host: str, manual: bool) -> None:
        if host in self.control_feeds:
            self.control_feeds[host].manual = manual

    # Processes the bounding box and sends commands
    @abstractmethod
    def process_frame(
        self,
        hostname: str,
        bounding_box: list,
        frame_shape: tuple,
        publisher: Publisher,
    ) -> Any:
        raise NotImplementedError("Subclasses must implement this method.")

    def track_obj(self) -> Any | None:
        all_bboxes = self.tracker.get_bboxes()
        for host, bboxes in all_bboxes.items():
            if host in self.control_feeds and bboxes is not None and len(bboxes) > 0:
                if self.control_feeds[host].manual:
                    continue  # skip manual feeds
                bbox = bboxes[0]
                if len(bboxes) > 1: # Find which bbox to track
                    match self.control_feeds[host].tracking_priority:
                        case "largest":
                            bbox = self.track_largest(bboxes)
                        case "smallest":
                            bbox = self.track_smallest(bboxes)
                return self.process_frame(
                    host,
                    bbox,
                    self.control_feeds[host].frame_shape,
                    self.control_feeds[host].publisher,
                )
            else:
                print(
                    "[NOTICE]Boundary box not found. Make sure the object recognition is running."
                )

    def start_auto_control(self) -> None:
        if self.scheduler is not None:
            self.control_task = self.scheduler.set_interval(
                1000 / DIRECTOR_CONTROL_RATE, self.track_obj
            )
            self._term = add_termination_handler(self.stop_auto_control)
        else:
            # TODO: implement this
            raise NotImplementedError("No GUI mode not implemented")

    def stop_auto_control(self) -> None:
        if self.control_task is not None:
            self.control_task.cancel()
        if self._term is not None:
            remove_termination_handler(self._term)
            self._term = None

    def track_largest(self, bboxes: list[list[int]]) -> list[int]:
        '''Returns the largest bounding box from a list of bounding boxes.'''
        largest_bbox = bboxes[0]
        largest_area = (largest_bbox[2] - largest_bbox[0]) * (largest_bbox[3] - largest_bbox[1])
        for bbox in bboxes:
            bbox_area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
            if bbox_area > largest_area:
                largest_bbox = bbox
                largest_area = bbox_area
        return largest_bbox

    def track_smallest(self, bboxes: list[list[int]]) -> list[int]:
        '''Returns the smallest bounding box from a list of bounding boxes.'''
        smallest_bbox = bboxes[0]
        smallest_area = (smallest_bbox[2] - smallest_bbox[0]) * (smallest_bbox[3] - smallest_bbox[1])
        for bbox in bboxes:
            bbox_area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
            if bbox_area < smallest_area:
                smallest_bbox = bbox
                smallest_area = bbox_area
        return smallest_bbox
    
