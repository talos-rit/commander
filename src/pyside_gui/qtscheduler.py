from PySide6.QtCore import QObject, QTimer, Signal, Slot
from src.scheduler import IterativeTask, Scheduler


class QTIterativeTask(IterativeTask):
    """Replacement for TKIterativeTask using QTimer"""

    def __init__(self, ms, func, *args):
        super().__init__()
        self.is_running = True
        self._stop_flag = False
        self._timer = QTimer()
        self._timer.timeout.connect(lambda: self._execute(func, *args))
        self._timer.start(ms)

    def _execute(self, func, *args):
        if not self._stop_flag:
            func(*args)
        else:
            self.cancel()

    def cancel(self):
        self._stop_flag = True
        self._timer.stop()
        self.is_running = False


class QTScheduler(Scheduler):
    """Replacement for TKScheduler using Qt timers"""

    def __init__(self):
        self._timers = []

    def set_timeout(self, ms, func, *args):
        """Execute function after ms milliseconds"""
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: func(*args))
        timer.start(ms)
        self._timers.append(timer)
        return timer

    def set_interval(self, ms, func, *args):
        """Execute function every ms milliseconds"""
        return QTIterativeTask(ms, func, *args)

    def cleanup(self):
        """Clean up all timers"""
        for timer in self._timers:
            if timer.isActive():
                timer.stop()
