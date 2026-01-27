from tkinter import Tk

from src.scheduler import IterativeTask, Scheduler


class TKIterativeTask(IterativeTask):
    root: Tk
    is_running = True
    _stop_flag = False
    _call_id: str | None = None
    _ms: int

    def __init__(self, root: Tk, ms: int, func, *args):
        super().__init__()
        self.root = root
        self._ms = ms
        self._args = args
        self._func = func
        self._iterative_call(self._func, *self._args)

    def _iterative_call(self, func, *args):
        self.root.after(self._ms, func, *args)
        if not self._stop_flag:
            self._call_id = self.root.after(self._ms, self._iterative_call, func, *args)
        else:
            self.is_running = False

    def cancel(self):
        self._stop_flag = True
        if self._call_id is not None:
            self.root.after_cancel(self._call_id)

    def set_interval(self, ms: int):
        self._ms = ms

    def get_interval(self) -> int:
        return self._ms


class TKScheduler(Scheduler):
    def __init__(self, root: Tk):
        self.root = root

    def set_timeout(self, ms, func, *args):
        if isinstance(ms, str) and ms.lower() == "idle":
            self.root.after_idle(func, *args)
        else:
            self.root.after(int(ms), func, *args)

    def set_interval(self, ms, func, *args):
        return TKIterativeTask(self.root, int(ms), func, *args)
