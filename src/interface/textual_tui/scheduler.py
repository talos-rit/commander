from textual.app import App

from src.talos_app import IterativeTask, Scheduler


class TextualIterativeTask(IterativeTask):
    def __init__(self, app: App, ms: int, func, args):
        self.app = app
        self._args = args
        self._ms = ms
        self._func = func
        self._timer = app.set_interval(
            ms / 1000,
            lambda: func(*args),
        )
        self.is_running = True

    def cancel(self):
        self._timer.stop()
        self.is_running = False

    def set_interval(self, ms: int):
        self._timer.stop()
        self._ms = ms
        seconds = ms / 1000
        self._timer = self.app.set_interval(
            seconds,
            lambda: self._func(*self._args),
        )

    def get_interval(self) -> int:
        return int(self._ms)


class TextualScheduler(Scheduler):
    def __init__(self, app: App):
        self.app = app  # A Textual App instance

    def set_timeout(self, ms, func, *args):
        seconds = ms / 1000
        return self.app.set_timer(seconds, lambda: func(*args))

    def set_interval(self, ms, func, *args):
        return TextualIterativeTask(self.app, ms, func, args)
