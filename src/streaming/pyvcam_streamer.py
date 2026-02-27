import time
import threading
from typing import Callable

from loguru import logger
import numpy as np
import pyvirtualcam as pyvcam
from src.utils import add_termination_handler, remove_termination_handler

class PyVcamStreamController:
    def __init__(self, frame_getter: Callable[[], np.ndarray | None]) -> None:
        self._frame_getter = frame_getter
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._term_id: int | None = None

    def start(self) -> None:
        self._is_running = True

        if self._term_id is None:
            self._term_id = add_termination_handler(self.stop)

        first_frame = self._wait_for_frame()
        height, width = first_frame.shape[:2]

        # TODO: Get FPS from somewhere in configs
        fps = 30
        self._thread = threading.Thread(
            target=self._stream_loop,
            args=(width, height, fps),
            name="pyvcam-stream",
            daemon=True,
        )
        self._thread.start()

    def stop(self, timeout_s: float = 2.0) -> None:
        logger.info("Stopping pyvcam stream")
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=timeout_s)
        self._stop_event.clear()
        if self._term_id is not None:
            remove_termination_handler(self._term_id)
            self._term_id = None

    def _wait_for_frame(self, timeout_s: float = 5.0) -> np.ndarray:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            frame = self._frame_getter()
            if frame is not None:
                return frame
            time.sleep(0.05)
        raise RuntimeError("Timed out waiting for a video frame")

    def _stream_loop(self, width: int, height: int, fps: int = 30) -> None:
        logger.info("Entering pyvcam stream loop with frame size {}x{}", width, height)
        with pyvcam.Camera(width=width, height=height, fps=fps, fmt=pyvcam.PixelFormat.BGR) as cam:
            while not self._stop_event.is_set():
                frame = self._frame_getter()
                if frame is not None:
                    cam.send(frame)
                    cam.sleep_until_next_frame()

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()
