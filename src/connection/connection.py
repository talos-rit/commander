from dataclasses import dataclass, field

import cv2
import numpy as np

from src.config import load_config
from src.connection.publisher import Publisher
from src.utils import add_termination_handler, remove_termination_handler


@dataclass
class VideoConnection:
    src: str | int
    video_buffer_size: int = field(default=1)
    cap: cv2.VideoCapture = field(init=False)
    shape: tuple | None = field(init=False, default=None)
    dtype: np.dtype | None = field(init=False, default=None)
    _term: int | None = field(init=False)

    def __post_init__(self):
        source = None
        try:
            source = int(self.src)
        except ValueError:
            source = self.src
        self.cap = cv2.VideoCapture(source)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, self.video_buffer_size)
        self._term = add_termination_handler(self.close)
        frame = None
        for _ in range(6):
            ret, frame = self.cap.read()
            if ret and frame is not None:
                self.shape = frame.shape
                self.dtype = frame.dtype
                return
        print("Unable to pull frame from camera")
        return

    @property
    def frame(self) -> np.ndarray | None:
        if self.cap is not None:
            _, frame = self.cap.read()
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
