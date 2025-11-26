from tkinter import Tk

from src.scheduler import IterativeTask, Scheduler


class TKIterativeTask(IterativeTask):
    root: Tk
    is_running = True
    _stop_flag = False
    _call_id: str | None = None

    def __init__(self, root: Tk, ms, func, *args):
        super().__init__()
        self.root = root
        self.iterative_call(int(ms), func, *args)

    def iterative_call(self, ms, func, *args):
        self._call_id = self.root.after(ms, func, *args)
        if not self._stop_flag:
            self.root.after(ms, self.iterative_call, ms, func, *args)
        else:
            self.is_running = False

    def cancel(self):
        self._stop_flag = True
        if self._call_id is not None:
            self.root.after_cancel(self._call_id)


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
