from __future__ import annotations

import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Callable

import cv2
import numpy as np
from loguru import logger

from src.utils import add_termination_handler, remove_termination_handler


@dataclass(frozen=True)
class StreamConfig:
    output_url: str
    fps: int | None = None
    use_docker: bool = False
    docker_image: str = "jrottenberg/ffmpeg:6.1-alpine"
    docker_network: str | None = None
    ffmpeg_bin: str = "ffmpeg"
    rtsp_transport: str = "tcp"
    preset: str = "veryfast"
    tune: str = "zerolatency"
    loglevel: str = "warning"


class FfmpegStreamController:
    def __init__(
        self,
        frame_getter: Callable[[], np.ndarray | None],
        config: StreamConfig,
    ) -> None:
        self._frame_getter = frame_getter
        self._config = config
        self._process: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._stderr_thread: threading.Thread | None = None
        self._term_id: int | None = None

    def start(self) -> None:
        if self._process is not None:
            logger.warning("Stream already running")
            return

        if self._term_id is None:
            self._term_id = add_termination_handler(self.stop)

        first_frame = self._wait_for_frame()
        height, width = first_frame.shape[:2]
        command = self._build_command(width, height)

        logger.info("Starting ffmpeg stream: {}", " ".join(command))
        self._process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

        self._stderr_thread = threading.Thread(
            target=self._drain_stderr, name="ffmpeg-stderr", daemon=True
        )
        self._stderr_thread.start()

        self._thread = threading.Thread(
            target=self._stream_loop,
            args=(width, height),
            name="ffmpeg-stream",
            daemon=True,
        )
        self._thread.start()

    def stop(self, timeout_s: float = 2.0) -> None:
        if self._process is None:
            return
        self._stop_event.set()

        if self._thread is not None:
            self._thread.join(timeout=timeout_s)

        try:
            if self._process.stdin:
                self._process.stdin.close()
        except Exception:
            pass

        self._process.terminate()
        try:
            self._process.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            self._process.kill()
        self._process = None
        self._stop_event.clear()
        if self._term_id is not None:
            remove_termination_handler(self._term_id)
            self._term_id = None

    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def _wait_for_frame(self, timeout_s: float = 5.0) -> np.ndarray:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            frame = self._frame_getter()
            if frame is not None:
                return frame
            time.sleep(0.05)
        raise RuntimeError("Timed out waiting for a video frame")

    def _stream_loop(self, width: int, height: int) -> None:
        logger.info("Entering ffmpeg stream loop with frame size {}x{}", width, height)
        assert self._process is not None
        assert self._process.stdin is not None

        while not self._stop_event.is_set():
            frame = self._frame_getter()
            if frame is None:
                time.sleep(0.01)
                continue

            if frame.shape[0] != height or frame.shape[1] != width:
                frame = cv2.resize(frame, (width, height))

            try:
                self._process.stdin.write(frame.tobytes())
                self._process.stdin.flush()
            except BrokenPipeError:
                logger.error("ffmpeg stdin closed; stopping stream")
                break

        self._stop_event.set()

    def _build_command(self, width: int, height: int) -> list[str]:
        cfg = self._config

        base_cmd = [
            cfg.ffmpeg_bin,
            "-f",
            "rawvideo",
            "-pix_fmt",
            "bgr24",
            "-s",
            f"{width}x{height}",
            "-fflags",
            "nobuffer",
            "-flags",
            "low_delay",
            "-i",
            "pipe:0",
            "-an",  # No audio
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-preset",
            cfg.preset or "ultrafast",
            "-tune",
            cfg.tune or "zerolatency",
        ]

        if cfg.output_url.startswith("rtsp://"):
            base_cmd += ["-f", "rtsp", "-rtsp_transport", cfg.rtsp_transport]
        elif cfg.output_url.startswith("rtmp://"):
            base_cmd += ["-f", "flv"]

        base_cmd.append(cfg.output_url)

        if not cfg.use_docker:
            return base_cmd

        container_name = f"commander-ffmpeg-{uuid.uuid4().hex[:8]}"
        docker_cmd = [
            "docker",
            "run",
            "--rm",
            "-i",
            "--name",
            container_name,
        ]
        if cfg.docker_network:
            docker_cmd += ["--network", cfg.docker_network]
        docker_cmd.append(cfg.docker_image)
        return docker_cmd + base_cmd

    def _drain_stderr(self) -> None:
        if self._process is None or self._process.stderr is None:
            return
        for line in self._process.stderr:
            try:
                text = line.decode("utf-8", errors="replace").strip()
            except Exception:
                text = str(line)
            if text:
                logger.debug("ffmpeg: {}", text)
