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
    connections: ConnectionCollection

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
        if (
            event == ConnectionCollectionEvent.ADDED
            and self.scheduler is not None
            and self.control_task is None
        ):
            self.start_auto_control()
        elif event == ConnectionCollectionEvent.REMOVED and not self.connections:
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
        for host, conn in self.connections.items():
            bbox = conn.get_bboxes()
            if host in self.connections and bbox is not None and len(bbox) > 0:
                video_conn = conn.video_connection
                if (
                    conn.is_manual
                    or video_conn is None
                    or (shape := video_conn.shape) is None
                ):
                    continue  # skip manual feeds
                return self.process_frame(
                    host,
                    bbox,
                    shape,
                    conn.publisher,
                )

    def is_active(self) -> bool:
        return self.control_task is not None

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

    def set_manual_control(
        self, hostname: str | None = None, manual: bool = True
    ) -> bool | None:
        """Sets the control mode of the connection. If hostname is None, sets the active connection.
        Returns the new control mode (True for manual, False for auto) or None if no connection is found."""
        conn = (
            self.connections.get_active()
            if hostname is None
            else self.connections.get(hostname)
        )
        if conn is None:
            logger.warning("No active connection found.")
            return None
        if conn.is_manual_only:
            logger.warning(f"Connection for hostname {hostname} is manual only.")
            conn.is_manual = True
            return False
        conn.is_manual = manual
        return conn.is_manual

    def get_manual_control(self, hostname: str | None = None) -> bool | None:
        """Gets the control mode of the connection. If hostname is None, gets the active connection.
        Returns the control mode (True for manual, False for auto) or None if no connection is found."""
        conn = (
            self.connections.get_active()
            if hostname is None
            else self.connections.get(hostname)
        )
        if conn is None:
            logger.warning("No active connection found.")
            return None
        return conn.is_manual
