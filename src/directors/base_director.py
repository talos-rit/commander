from abc import ABC, abstractmethod
from typing import Any

from src.connection.connection import Connection
from src.connection.publisher import Publisher
from src.scheduler import IterativeTask, Scheduler
from src.utils import add_termination_handler, remove_termination_handler

DIRECTOR_CONTROL_RATE = 10  # control per sec


class BaseDirector(ABC):
    scheduler: Scheduler | None
    control_task: IterativeTask | None = None
    _term: int | None = None
    connections: dict[str, Connection]

    def __init__(
        self,
        tracker,
        connections: dict[str, Connection],
        scheduler: Scheduler | None = None,
    ):
        self.tracker = tracker
        self.scheduler = scheduler
        self.connections = connections
        self.start_auto_control()

    def add_connection(
        self, connection: Connection
    ):
        self.connections[connection.host] = connection
        if self.scheduler is not None and self.control_task is None:
            self.start_auto_control()

    def remove_control_feed(self, host: str) -> None:
        if host in self.connections:
            del self.connections[host]
        if not self.connections:
            self.stop_auto_control()

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
        bboxes = self.tracker.get_bboxes()
        for host, bbox in bboxes.items():
            if host in self.connections and bbox is not None and len(bbox) > 0:
                if self.connections[host].is_manual or (shape:=self.connections[host].video_connection.shape) is None:
                    continue  # skip manual feeds
                return self.process_frame(
                    host,
                    bbox,
                    shape,
                    self.connections[host].publisher,
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
