"""System FFmpeg capture for Pi V4L2 hardware decoding.

OpenCV wheels bundle their own FFmpeg and may omit h264_v4l2m2m even when
/usr/bin/ffmpeg supports it. This adapter uses the system decoder explicitly.
"""
import collections
import os
import subprocess
import threading

import numpy as np
from loguru import logger


class FFmpegCapture:
    def __init__(self, source, decoder="h264_v4l2m2m", width=640, height=480):
        width, height = int(os.getenv("CAPTURE_WIDTH", str(width))), int(os.getenv("CAPTURE_HEIGHT", str(height)))
        self.width, self.height = width, height
        self.decoder = decoder
        self._frame = None
        self._errors = collections.deque(maxlen=6)
        command = [os.getenv("FFMPEG_BINARY", "ffmpeg"), "-hide_banner", "-nostats", "-loglevel", "info",
                   "-rtsp_transport", "tcp", "-fflags", "nobuffer", "-flags", "low_delay",
                   "-threads", "1", "-filter_threads", "1", "-c:v", decoder, "-i", str(source),
                   "-an", "-vf", f"scale={width}:{height}", "-pix_fmt", "bgr24",
                   "-threads", "1", "-f", "rawvideo", "pipe:1"]
        self.process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self._drainer = threading.Thread(target=self._drain_stderr, daemon=True)
        self._drainer.start()

    def _drain_stderr(self):
        for raw in self.process.stderr:
            line = raw.decode(errors="replace").strip()
            self._errors.append(line)
            if "Using device" in line or "Stream mapping" in line or "h264_v4l2m2m" in line:
                logger.info("[Capture/FFmpeg] {}", line)

    def isOpened(self):
        return self.process.poll() is None

    def set(self, *_):
        return False

    def grab(self):
        # Buffered pipe reads collect one whole image. No inference queue exists;
        # CameraStream continuously drains this process on its capture thread.
        data = self.process.stdout.read(self.width * self.height * 3)
        if len(data) != self.width * self.height * 3:
            logger.warning("[Capture/FFmpeg] {} stopped: {}", self.decoder, " | ".join(self._errors))
            return False
        self._frame = np.frombuffer(data, dtype=np.uint8).reshape(self.height, self.width, 3)
        return True

    def retrieve(self):
        return self._frame is not None, self._frame

    def release(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
        self._drainer.join(timeout=1)
