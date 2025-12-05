from textual.app import App
from textual.timer import Timer

from src.talos_app import IterativeTask, Scheduler


class TextualIterativeTask(IterativeTask):
    def __init__(self, timer: Timer):
        self._timer: Timer = timer
        self.is_running = True

    def cancel(self):
        self._timer.stop()
        self.is_running = False


class TextualScheduler(Scheduler):
    def __init__(self, app: App):
        self.app = app  # A Textual App instance

    def set_timeout(self, ms, func, *args):
        seconds = ms / 1000

        self.app.set_timer(seconds, lambda: func(*args))

    def set_interval(self, ms, func, *args):
        seconds = ms / 1000

        timer = self.app.set_interval(
            seconds,
            lambda: func(*args),
        )

        return TextualIterativeTask(timer)
