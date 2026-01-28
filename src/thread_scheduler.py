import threading
from typing import Callable

from loguru import logger

from src.scheduler import IterativeTask, Scheduler


class ThreadIterativeTask(IterativeTask):
    def __init__(
        self, scheduler: "ThreadScheduler", interval_ms: int, func: Callable, *args
    ):
        self.scheduler = scheduler
        self._interval_ms = interval_ms
        self._func = func
        self._args = args
        self.is_running = True
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()
        self._schedule_next()

    def _schedule_next(self):
        """Schedule the next execution."""
        with self._lock:
            if not self.is_running:
                return
            self._timer = threading.Timer(self._interval_ms / 1000.0, self._execute)
            self._timer.daemon = True
            self._timer.start()

    def _execute(self):
        """Execute the function and reschedule."""
        if not self.is_running:
            return
        try:
            self._func(*self._args)
        except Exception as e:
            logger.error(f"Error in scheduled task: {e}")
        finally:
            self._schedule_next()

    def cancel(self, wait: bool = True):
        """Cancel the recurring task."""
        with self._lock:
            self.is_running = False
            if self._timer is not None:
                self._timer.cancel()
                self._timer.join() if wait else None
                self._timer = None

    def set_interval(self, ms: int):
        """Change the interval and reschedule."""
        with self._lock:
            self._interval_ms = ms
            if self._timer is not None:
                self._timer.cancel()
            if self.is_running:
                self._timer = threading.Timer(ms / 1000.0, self._execute)
                self._timer.daemon = True
                self._timer.start()

    def get_interval(self) -> int:
        """Get the current interval in milliseconds."""
        return self._interval_ms


class ThreadScheduler(Scheduler):
    def set_timeout(self, ms: int, func: Callable, *args):
        """Set a timeout to call func after ms milliseconds."""
        timer = threading.Timer(ms / 1000.0, func, args)
        timer.daemon = True
        timer.start()
        return timer

    def set_interval(self, ms: int, func: Callable, *args) -> IterativeTask:
        """
        Calls func every ms milliseconds.
        Return a ThreadIterativeTask instance.
        """
        return ThreadIterativeTask(self, ms, func, *args)
