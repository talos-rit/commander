import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

import av
import av.error
import av.video
import cv2
import numpy as np
from loguru import logger

import src.config as config
from src.connection.publisher import Publisher
from src.utils import (
    add_termination_handler,
    remove_termination_handler,
)

# Keep the RTSP demuxer from buffering a live stream. TCP is still used for
# reliability; a dedicated capture thread drains packets so latency cannot grow.
RTSP_OPEN_OPTIONS = {
    "rtsp_transport": "tcp",
    "fflags": "nobuffer",
    "flags": "low_delay",
    "max_delay": "0",
    "reorder_queue_size": "0",
}
RTSP_OPEN_TIMEOUT = (2.0, 1.0)


class PyAVCapture:
    _term: int | None = None

    def __init__(self, source, **options):
        self._released = False
        self._source = source
        self.container = av.open(
            source,
            options=options or None,
            timeout=RTSP_OPEN_TIMEOUT,
        )
        self.video_stream = next(
            (s for s in self.container.streams if s.type == "video"), None
        )
        if not self.video_stream:
            raise ValueError("No video stream found")
        self._configure_low_latency()
        self.iter_frames = self._get_frame_iter()
        self.more = True
        self._term = add_termination_handler(self.release)

    def _configure_low_latency(self) -> None:
        ctx = getattr(self.video_stream, "codec_context", None)
        if ctx is None:
            return
        flags = getattr(av.codec.context, "Flags", None)
        low_delay = getattr(flags, "low_delay", None) if flags is not None else None
        if low_delay is None:
            return
        try:
            ctx.flags |= low_delay
        except Exception:
            pass

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
        if self._released or not self.more:
            return False, None, None
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
        except av.error.FFmpegError as exc:
            logger.warning("RTSP demux error from {}: {}", self._source, exc)
            self.more = False
            return False, None, None

    def release(self):
        if self._released:
            return
        self._released = True
        self.more = False
        try:
            self.container.close()
        except Exception as exc:
            logger.debug("Error closing RTSP container: {}", exc)
        if self._term is not None:
            remove_termination_handler(self._term)
            self._term = None


@dataclass
class VideoConnection:
    src: str | int
    video_buffer_size: int = field(default=1)
    first_frame_timeout: float = field(default=5.0)
    reconnect_delay: float = field(default=1.0)
    cap: cv2.VideoCapture | PyAVCapture | None = field(init=False, default=None)
    shape: tuple | None = field(init=False, default=None)
    dtype: np.dtype | None = field(init=False, default=None)
    _term: int | None = field(init=False, default=None)
    _frame_lock: threading.Lock = field(init=False, default_factory=threading.Lock)
    _cap_lock: threading.Lock = field(init=False, default_factory=threading.Lock)
    _latest_frame: np.ndarray | None = field(init=False, default=None)
    _stop_event: threading.Event = field(init=False, default_factory=threading.Event)
    _thread: threading.Thread | None = field(init=False, default=None)

    def __post_init__(self):
        self._open_capture()
        self._thread = threading.Thread(
            target=self._capture_loop,
            name=f"video-capture-{self.src}",
            daemon=True,
        )
        self._thread.start()
        self._term = add_termination_handler(self.close)
        self._wait_for_first_frame()
        if self.shape is None:
            logger.warning("Unable to pull frame from camera")

    def _resolve_source(self) -> str | int:
        try:
            return int(self.src)
        except (TypeError, ValueError):
            return self.src

    def _open_capture(self) -> None:
        if self._stop_event.is_set():
            return
        source = self._resolve_source()
        if isinstance(source, str) and source.startswith("rtsp://"):
            try:
                new_cap: cv2.VideoCapture | PyAVCapture = PyAVCapture(
                    source, **RTSP_OPEN_OPTIONS
                )
            except Exception as exc:
                if self._stop_event.is_set():
                    return
                logger.warning(
                    "Failed to open RTSP stream with low-latency options ({}). Retrying with TCP only.",
                    exc,
                )
                new_cap = PyAVCapture(source, rtsp_transport="tcp")
        else:
            new_cap = cv2.VideoCapture(source)
            new_cap.set(cv2.CAP_PROP_BUFFERSIZE, self.video_buffer_size)
        with self._cap_lock:
            self._release_capture_unlocked()
            if self._stop_event.is_set():
                try:
                    new_cap.release()
                except Exception:
                    pass
                return
            self.cap = new_cap

    def _release_capture_unlocked(self) -> None:
        cap = self.cap
        self.cap = None
        if cap is None:
            return
        try:
            cap.release()
        except Exception as exc:
            logger.debug("Error releasing video capture for {}: {}", self.src, exc)

    def _release_capture(self) -> None:
        with self._cap_lock:
            self._release_capture_unlocked()

    def _wait_for_first_frame(self) -> None:
        deadline = time.monotonic() + self.first_frame_timeout
        while self.shape is None and time.monotonic() < deadline:
            if self._stop_event.is_set():
                return
            time.sleep(0.01)

    def _capture_loop(self) -> None:
        while not self._stop_event.is_set():
            with self._cap_lock:
                cap = self.cap
            if cap is None:
                self._reconnect()
                continue
            try:
                result = cap.read()
            except Exception as exc:
                if self._stop_event.is_set():
                    break
                logger.warning("Video read failed from {}: {}", self.src, exc)
                self._reconnect()
                continue
            ret, frame, *_ = result if isinstance(result, tuple) else (False, None)
            if ret and frame is not None:
                owned = np.copy(frame)
                with self._frame_lock:
                    self._latest_frame = owned
                    self.shape = owned.shape
                    self.dtype = owned.dtype
                continue
            if self._stop_event.is_set():
                break
            logger.warning("Lost video stream from {}, reconnecting", self.src)
            self._reconnect()

    def _reconnect(self) -> None:
        if self._stop_event.is_set():
            return
        self._release_capture()
        if self._stop_event.wait(self.reconnect_delay):
            return
        try:
            self._open_capture()
        except Exception as exc:
            logger.warning("Failed to reconnect to {}: {}", self.src, exc)

    def get_frame(self) -> np.ndarray | None:
        with self._frame_lock:
            frame = self._latest_frame
        if frame is None:
            return None
        return frame.copy()

    def close(self):
        if self._stop_event.is_set() and self._thread is None:
            return
        self._stop_event.set()
        self._release_capture()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=5.0)
            if thread.is_alive():
                logger.warning("Capture thread for {} did not stop cleanly", self.src)
        self._thread = None
        with self._frame_lock:
            self._latest_frame = None
        if self._term is not None:
            remove_termination_handler(self._term)
            self._term = None
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
        self.is_manual_only = config.ROBOT_CONFIGS[self.host].manual_only

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
            super().__delitem__(key)
            self._notify_listeners(ConnectionCollectionEvent.REMOVED, key, connection)
            connection.close()
            if key == self._active_host:
                new_host = next((h for h in self if h != key), None)
                self.set_active(new_host)

    def pop(self, key: str, default: Any = None) -> Connection | Any:
        """Pops the connection and notifies the listeners of removal. If connection is active, sets active connection to another available connection or None."""
        connection = super().pop(key, None)
        if connection is not None:
            self._notify_listeners(ConnectionCollectionEvent.REMOVED, key, connection)
            connection.close()
            if key == self._active_host:
                new_host = next((h for h in self if h != key), None)
                self.set_active(new_host)
        return connection or default

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
