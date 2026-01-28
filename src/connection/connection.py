import threading
import time
from dataclasses import dataclass, field

import av
import cv2
import numpy as np
from loguru import logger

from src.config import load_config
from src.connection.publisher import Publisher
from src.utils import add_termination_handler, remove_termination_handler


class PyAVCapture:
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
        for packet in self.container.demux(self.video_stream):
            for frame in packet.decode():
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
        self._term = add_termination_handler(self.close)
        frame = None
        for _ in range(6):
            ret, frame, *rest = self.cap.read()
            logger.info(f"{rest=}")
            if ret and frame is not None:
                self.shape = frame.shape
                self.dtype = frame.dtype
                return
        logger.warning("Unable to pull frame from camera")
        return

    def get_frame(self) -> np.ndarray | None:
        if self.cap is not None:
            with self._read_lock:
                r, frame, *rest = self.cap.read()
                logger.info(f"{rest=}")
            if not r:
                return None
            return frame

    def close(self):
        if self.cap is not None:
            self.cap.release()
        if self._term is not None:
            remove_termination_handler(self._term)
            self._term = None


@dataclass
class Connection:
    host: str
    port: int
    video_connection: VideoConnection
    publisher: Publisher = field(init=False)
    is_manual: bool = True
    is_manual_only: bool = field(
        default_factory=lambda: load_config().get("default_manual_only", False)
    )
    fps: int = field(default_factory=lambda: load_config().get("default_fps", 60))

    def __post_init__(self):
        self.publisher = Publisher(self.host, self.port)

    def set_manual(self, manual: bool) -> None:
        self.is_manual = manual

    def toggle_manual(self) -> None:
        self.is_manual = not self.is_manual

    def close(self) -> None:
        self.publisher.close()
