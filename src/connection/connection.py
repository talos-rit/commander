import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

import av
import av.error
import av.video
import cv2
import numpy as np
from loguru import logger

import src.config as config
from src.connection.publisher import Publisher
from src.observations.types import BBox, FramePacket, PersonObservation
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
    "use_wallclock_as_timestamps": "1",
}
RTSP_FALLBACK_OPTIONS = {"rtsp_transport": "tcp", "use_wallclock_as_timestamps": "1"}
RTSP_OPEN_TIMEOUT = (2.0, 1.0)


def is_live_source(src: str | int) -> bool:
    """Prerecorded files must advance deterministically; everything else is live."""
    try:
        int(src)
        return True
    except (TypeError, ValueError):
        return not Path(str(src)).is_file()


class PyAVCapture:
    _term: int | None = None

    def __init__(self, source, **options):
        self._released = False
        self._source = source
        self.container = av.open(
            source, options=options or None, timeout=RTSP_OPEN_TIMEOUT
        )
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
        remove_termination_handler(self._term) if self._term is not None else None
        self._term = None


@dataclass
class VideoConnection:
    src: str | int
    video_buffer_size: int = field(default=1)
    camera_id: str | None = None
    timestamp_provider: Callable[[], float] = field(
        default=time.time, repr=False, compare=False
    )
    background_capture: bool = False
    """When True, a daemon thread continuously drains the source into a
    latest-packet buffer and capture_packet() returns that buffer instead of
    advancing the source. Use for live sources (RTSP, webcams)."""
    first_frame_timeout: float = field(default=5.0)
    reconnect_delay: float = field(default=1.0)
    cap: cv2.VideoCapture | PyAVCapture | None = field(init=False, default=None)
    shape: tuple | None = field(init=False, default=None)
    dtype: np.dtype | None = field(init=False, default=None)
    _term: int | None = field(init=False, default=None)
    _read_lock: threading.Lock = field(init=False, default_factory=threading.Lock)
    """Guards the cached packet; never held across a blocking source read."""
    _cap_lock: threading.Lock = field(init=False, default_factory=threading.Lock)
    _frame_sequence: int = field(init=False, default=-1)
    _latest_packet: FramePacket | None = field(init=False, default=None)
    _is_prerecorded: bool = field(init=False, default=False)
    _stop_event: threading.Event = field(init=False, default_factory=threading.Event)
    _thread: threading.Thread | None = field(init=False, default=None)

    def __post_init__(self):
        source = self._resolve_source()
        if self.camera_id is None:
            self.camera_id = str(self.src)
        self._is_prerecorded = isinstance(source, str) and Path(source).is_file()
        self.cap = self._open_capture(source)
        if self.background_capture:
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
            return
        for _ in range(6):
            if (packet := self.capture_packet()) is not None:
                self.shape = packet.image.shape
                self.dtype = packet.image.dtype
                return
        logger.warning("Unable to pull frame from camera")

    def _resolve_source(self) -> str | int:
        try:
            return int(self.src)
        except (TypeError, ValueError):
            return self.src

    def _open_capture(self, source: str | int) -> cv2.VideoCapture | PyAVCapture:
        if isinstance(source, str) and source.startswith("rtsp://"):
            try:
                return PyAVCapture(source, **RTSP_OPEN_OPTIONS)
            except Exception as exc:
                logger.warning(
                    "Failed to open RTSP stream with low-latency options ({}). Retrying with TCP only.",
                    exc,
                )
                return PyAVCapture(source, **RTSP_FALLBACK_OPTIONS)
        cap = cv2.VideoCapture(source)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, self.video_buffer_size)
        return cap

    def _read_packet(self) -> FramePacket | None:
        """Advance the underlying source once and cache the resulting packet."""

        with self._cap_lock:
            cap = self.cap
            if cap is None:
                return None
            ret, frame, *rest = cap.read()
        if not ret or frame is None:
            return None
        timestamp = self._capture_timestamp(rest, cap)
        with self._read_lock:
            self._frame_sequence += 1
            packet = FramePacket(
                camera_id=self.camera_id or str(self.src),
                frame_sequence=self._frame_sequence,
                capture_timestamp=timestamp,
                image=frame,
            )
            self._latest_packet = packet
            if self.shape is None:
                self.shape = frame.shape
                self.dtype = frame.dtype
            return packet

    def _wait_for_first_frame(self) -> None:
        deadline = time.monotonic() + self.first_frame_timeout
        while self.shape is None and time.monotonic() < deadline:
            if self._stop_event.wait(0.01):
                return

    def _capture_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                packet = self._read_packet()
            except Exception as exc:
                if self._stop_event.is_set():
                    break
                logger.warning("Video read failed from {}: {}", self.src, exc)
                packet = None
            if packet is not None:
                continue
            if self._stop_event.is_set():
                break
            logger.warning("Lost video stream from {}, reconnecting", self.src)
            self._reconnect()

    def _reconnect(self) -> None:
        with self._cap_lock:
            cap, self.cap = self.cap, None
        if cap is not None:
            try:
                cap.release()
            except Exception as exc:
                logger.debug("Error releasing video capture for {}: {}", self.src, exc)
        if self._stop_event.wait(self.reconnect_delay):
            return
        try:
            new_cap = self._open_capture(self._resolve_source())
        except Exception as exc:
            logger.warning("Failed to reconnect to {}: {}", self.src, exc)
            return
        with self._cap_lock:
            if self._stop_event.is_set():
                new_cap.release()
                return
            self.cap = new_cap

    def capture_packet(self) -> FramePacket | None:
        """Acquire a packet for this capture cycle.

        Synchronous sources advance once. Background sources return the newest
        drained packet so consumers never pull from the demuxer directly.
        """

        if self.background_capture:
            return self.get_latest_packet()
        return self._read_packet()

    def get_latest_packet(self) -> FramePacket | None:
        """Return the cached packet without advancing the video source."""

        with self._read_lock:
            return self._latest_packet

    def get_latest_frame(self) -> np.ndarray | None:
        packet = self.get_latest_packet()
        return packet.image if packet is not None else None

    def set_camera_id(self, camera_id: str) -> None:
        """Associate this source with a Connection while preserving its frame."""

        with self._read_lock:
            self.camera_id = camera_id
            if self._latest_packet is not None:
                self._latest_packet = FramePacket(
                    camera_id=camera_id,
                    frame_sequence=self._latest_packet.frame_sequence,
                    capture_timestamp=self._latest_packet.capture_timestamp,
                    image=self._latest_packet.image,
                )

    def get_frame(self) -> np.ndarray | None:
        """Legacy advancing API. New consumers should use packet methods explicitly."""

        packet = self.capture_packet()
        return packet.image if packet is not None else None

    def _capture_timestamp(self, read_metadata: list[Any], cap: Any = None) -> float:
        cap = cap if cap is not None else self.cap
        if read_metadata and read_metadata[0] is not None:
            return float(read_metadata[0])
        if self._is_prerecorded and hasattr(cap, "get"):
            position_ms = cap.get(cv2.CAP_PROP_POS_MSEC)
            if isinstance(position_ms, (int, float)) and np.isfinite(position_ms):
                return float(position_ms) / 1000.0
        return float(self.timestamp_provider())

    def close(self):
        self._stop_event.set()
        thread, self._thread = self._thread, None
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=5.0)
            if thread.is_alive():
                logger.warning("Capture thread for {} did not stop cleanly", self.src)
        # Releasing a PyAV container while another thread is inside read() frees
        # decoder state under it and crashes the process, so wait for the reader.
        if not self._cap_lock.acquire(timeout=5.0):
            logger.warning("Video capture for {} is still busy; not releasing it", self.src)
        else:
            try:
                cap, self.cap = self.cap, None
                if cap is not None:
                    cap.release()
                    logger.debug(f"Released video connection to {self.src}")
            finally:
                self._cap_lock.release()
        if self._term is not None:
            remove_termination_handler(self._term)
            self._term = None


@dataclass
class Connection:
    host: str
    port: int
    video_connection: VideoConnection | None
    is_manual: bool = True
    publisher_factory: Callable[[str, int], Publisher] = field(
        default=lambda host, port: Publisher(host, port), repr=False, compare=False
    )
    publisher: Publisher = field(init=False)
    _bboxes: list[BBox] | None = field(init=False, default=None)
    _observations: list[PersonObservation] | None = field(init=False, default=None)
    _bboxes_lock: threading.Lock = field(init=False, default_factory=threading.Lock)

    def __post_init__(self):
        self.publisher = self.publisher_factory(self.host, self.port)
        if self.video_connection is not None:
            self.video_connection.set_camera_id(self.host)
        self.is_manual_only = config.ROBOT_CONFIGS[self.host].manual_only

    def close(self) -> None:
        if self.video_connection is not None:
            self.video_connection.close()
        self.publisher.close()

    def get_bboxes(self) -> list[BBox] | None:
        with self._bboxes_lock:
            return self._bboxes

    def set_bboxes(self, bboxes: list[BBox] | None) -> None:
        with self._bboxes_lock:
            self._bboxes = bboxes
            self._observations = None

    def get_observations(self) -> list[PersonObservation] | None:
        with self._bboxes_lock:
            return self._observations

    def set_observations(
        self, observations: list[PersonObservation] | None
    ) -> None:
        """Store rich observations and maintain the legacy bounding-box view."""

        with self._bboxes_lock:
            self._observations = observations
            self._bboxes = (
                [observation.bounding_box for observation in observations]
                if observations is not None
                else None
            )


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
            connection.set_observations(None)
