from abc import ABC, abstractmethod
from typing import Any

from loguru import logger

from src.connection.connection import ConnectionCollectionEvent
from src.connection.publisher import Publisher
from src.scheduler import IterativeTask, Scheduler
from src.talos_app import ConnectionCollection
from src.utils import add_termination_handler, remove_termination_handler

DIRECTOR_CONTROL_RATE = 10  # control per sec


class BaseDirector(ABC):
    scheduler: Scheduler | None
    control_task: IterativeTask | None = None
    _term: int | None = None

    def __init__(
        self,
        tracker,
        connections: ConnectionCollection,
        scheduler: Scheduler | None = None,
    ):
        self.tracker = tracker
        self.scheduler = scheduler
        self.connections = connections
        self.connections.add_listener(self.on_connection_update)
        if len(self.connections) > 0 and self.scheduler is not None:
            self.start_auto_control()

    def on_connection_update(self, event: ConnectionCollectionEvent, *_: Any):
        if event == ConnectionCollectionEvent.ADDED:
            if self.scheduler is not None and self.control_task is None:
                self.start_auto_control()
        elif event == ConnectionCollectionEvent.REMOVED:
            if not self.connections:
                self.stop_auto_control()
        else:
            pass

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
                if self.connections[host].is_manual:
                    continue  # skip manual feeds
                assert (
                    frame_shape := self.connections[host].video_connection.shape
                ) is not None
                return self.process_frame(
                    host,
                    bbox,
                    frame_shape,
                    self.connections[host].publisher,
                )
            else:
                logger.warning(
                    f"Boundary box not found for host {host}. Make sure the object recognition is running."
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
