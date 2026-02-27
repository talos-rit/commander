import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

import av
import av.video
import cv2
import numpy as np
from loguru import logger

from src.config import ROBOT_CONFIGS
from src.connection.publisher import Publisher
from src.utils import (
    add_termination_handler,
    remove_termination_handler,
)


class PyAVCapture:
    _term: int | None = None

    def __init__(self, source, **options):
        self.container = av.open(source, options=options)
        self.video_stream = next(
            (s for s in self.container.streams if s.type == "video"), None
        )
        if not self.video_stream:
            raise ValueError("No video stream found")
        self.iter_frames = self._get_frame_iter()
        self.more = True
        self._term = add_termination_handler(self.release)

    def _get_frame_iter(self):
        """
        Generator that yields decoded video frames from the container.

        Iterates through packets from the demultiplexed video stream and decodes
        each packet into individual frames, yielding them one at a time.

        Yields:
            frame: A decoded video frame from the packet.
        """
        for packet in self.container.demux(self.video_stream):
            for frame in packet.decode():
                if isinstance(frame, av.video.frame.VideoFrame):
                    yield frame

    def read(self):
        try:
            frame = next(self.iter_frames)
            # BGR like OpenCV
            img = frame.to_ndarray(format="bgr24")  # pyright: ignore[reportAttributeAccessIssue]
            # pull absolute time stamp from rtsp stream if available
            raw_time = (
                frame.pts * self.video_stream.time_base
                if self.video_stream is not None
                and self.video_stream.time_base is not None
                else None
            )
            absolute_time = None
            if raw_time is not None:
                absolute_time = (
                    time.time() - (self.container.start_time / av.time_base) + raw_time
                )
            return True, img, absolute_time
        except StopIteration:
            self.more = False
            return False, None, None

    def release(self):
        self.container.close()
        remove_termination_handler(self._term) if self._term is not None else None
        self._term = None


@dataclass
class VideoConnection:
    src: str | int
    video_buffer_size: int = field(default=1)
    cap: cv2.VideoCapture | PyAVCapture = field(init=False)
    shape: tuple | None = field(init=False, default=None)
    dtype: np.dtype | None = field(init=False, default=None)
    _term: int | None = field(init=False)
    _read_lock: threading.Lock = field(init=False, default_factory=threading.Lock)

    def __post_init__(self):
        source = None
        try:
            source = int(self.src)
        except ValueError:
            source = self.src
        if isinstance(source, str) and source.startswith("rtsp://"):
            self.cap = PyAVCapture(
                source, rtsp_transport="tcp", use_wallclock_as_timestamps="1"
            )
        else:
            self.cap = cv2.VideoCapture(source)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, self.video_buffer_size)
        frame = None
        for _ in range(6):
            ret, frame, *rest = self.cap.read()
            if len(rest) > 0:
                logger.debug(f"{rest=}")
            if ret and frame is not None:
                self.shape = frame.shape
                self.dtype = frame.dtype
                return
        logger.warning("Unable to pull frame from camera")
        return

    def get_frame(self) -> np.ndarray | None:
        if self.cap is not None:
            with self._read_lock:
                r, frame, *rest = (
                    self.cap.read()
                )  # rest sometimes have timestamp info from PyAVCapture
            if not r:
                return None
            return frame

    def close(self):
        if self.cap is not None:
            self.cap.release()
            logger.debug(f"Released video connection to {self.src}")


@dataclass
class Connection:
    host: str
    port: int
    video_connection: VideoConnection | None
    is_manual: bool = True
    publisher: Publisher = field(init=False)
    _bboxes: list[tuple[int, int, int, int]] | None = field(init=False, default=None)
    _bboxes_lock: threading.Lock = field(init=False, default_factory=threading.Lock)

    def __post_init__(self):
        self.publisher = Publisher(self.host, self.port)
        self.is_manual_only = ROBOT_CONFIGS[self.host].manual_only

    def set_manual(self, manual: bool) -> None:
        self.is_manual = manual

    def toggle_manual(self) -> bool:
        self.is_manual = not self.is_manual
        return self.is_manual

    def close(self) -> None:
        if self.video_connection is not None:
            self.video_connection.close()
        self.publisher.close()

    def get_bboxes(self) -> list[tuple[int, int, int, int]] | None:
        with self._bboxes_lock:
            return self._bboxes

    def set_bboxes(self, bboxes: list[tuple[int, int, int, int]] | None) -> None:
        with self._bboxes_lock:
            self._bboxes = bboxes


class ConnectionCollectionEvent(Enum):
    ADDED = "added"
    REMOVED = "removed"
    ACTIVE_CHANGED = "active_changed"


class ConnectionCollection(dict[str, Connection]):
    _active_host: str | None = None
    _listeners: list[
        Callable[[ConnectionCollectionEvent, str, Connection | None], None]
    ] = []
    _term: int | None = None

    def set_active(self, hostname: str | None) -> Connection | None:
        if hostname is None:
            self._active_host = None
            self._notify_listeners(
                ConnectionCollectionEvent.ACTIVE_CHANGED, "None", None
            )
            return None
        if hostname not in self or (conn := self.get(hostname)) is None:
            logger.error(f"Connection to {hostname} does not exist")
            return None
        self._active_host = hostname
        self._notify_listeners(ConnectionCollectionEvent.ACTIVE_CHANGED, hostname, conn)
        if hostname is not None and self._term is None:
            self._term = add_termination_handler(self.clear)
        return self.get_active()

    def get_active(self) -> Connection | None:
        if self._active_host is None:
            return None
        return self.get(self._active_host, None)

    def add_listener(
        self,
        listener: Callable[[ConnectionCollectionEvent, str, Connection | None], None],
    ) -> None:
        self._listeners.append(listener)

    def remove_listener(
        self,
        listener: Callable[[ConnectionCollectionEvent, str, Connection | None], None],
    ) -> None:
        self._listeners.remove(listener)

    def _notify_listeners(
        self,
        event: ConnectionCollectionEvent,
        hostname: str,
        connection: Connection | None,
    ) -> None:
        for listener in self._listeners:
            listener(event, hostname, connection)

    def __setitem__(self, hostname: str, connection: Connection) -> None:
        super().__setitem__(hostname, connection)
        self._notify_listeners(ConnectionCollectionEvent.ADDED, hostname, connection)
        self.set_active(hostname)

    def __delitem__(self, key: str) -> None:
        if key in self:
            connection = self[key]
            self._notify_listeners(ConnectionCollectionEvent.REMOVED, key, connection)
            connection.close()
            if key == self._active_host:
                new_host = next((h for h in self if h != key), None)
                self.set_active(new_host)
        return super().__delitem__(key)

    def pop(self, key: str, default=None) -> Connection | None:
        """Pops the connection and notifies the listeners of removal. If connection is active, sets active connection to another available connection or None."""
        if key in self:
            connection = self[key]
            self._notify_listeners(ConnectionCollectionEvent.REMOVED, key, connection)
            connection.close()
            if key == self._active_host:
                new_host = next((h for h in self if h != key), None)
                self.set_active(new_host)
        return super().pop(key, default)

    def clear(self) -> None:
        self.set_active(None)
        while self:
            key, connection = self.popitem()
            self._notify_listeners(ConnectionCollectionEvent.REMOVED, key, connection)
            connection.close()
            self.set_active(None)
        if self._term is not None:
            remove_termination_handler(self._term)
            self._term = None

    def clear_bboxes(self) -> None:
        for connection in self.values():
            connection.set_bboxes(None)
