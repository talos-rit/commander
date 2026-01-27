import time
from pathlib import Path
from threading import Lock


class FPSLogger:
    _lock: Lock = Lock()

    def __init__(
        self, perf_file: str, perf_dir: Path = Path(".log"), debug: bool = True
    ):
        """Counts how frequently the tick is called

        Args:
            perf_file (str): name of the performance log file.
            perf_dir (Path, optional): directory to save the performance log file. Defaults to Path(".log").
            debug (bool, optional): Turn on or off the text file logger. Defaults to True.
        """
        self.debug = debug
        self.frame_count = 0
        self.start_time = time.time()
        self.fps = 0.0
        if self.debug:
            self.perf_file = perf_dir / perf_file.format(
                **{"time": time.strftime("%Y%m%d-%H%M%S")}
            )
            with open(self.perf_file, "w") as f:
                f.write("Time,FPS,Marker\n")

    def tick(self):
        if not self.debug:
            return
        with self._lock:
            self.frame_count += 1
            elapsed_time = time.time() - self.start_time
            if elapsed_time >= 1.0:
                self.fps = self.frame_count / elapsed_time
                self.frame_count = 0
                self.start_time = time.time()
            with open(self.perf_file, "a") as f:
                f.write(f"{time.time()},{self.fps},\n")

    def add_marker(self, marker_name: str):
        """Add a marker to indicate a significant event."""
        if not self.debug:
            return
        with self._lock, open(self.perf_file, "a") as f:
            f.write(f"{time.time()},{self.fps},{marker_name}\n")
