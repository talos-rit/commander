from abc import ABC, abstractmethod


class IterativeTask(ABC):
    is_running = True

    @abstractmethod
    def cancel(self):
        pass


class Scheduler(ABC):
    @abstractmethod
    def set_timeout(self, ms, func, *args):
        """Set a timeout to call func after ms milliseconds."""
        pass

    @abstractmethod
    def set_interval(self, ms, func, *args) -> IterativeTask:
        """
        Calls func every ms milliseconds.
        Return an IterativeTask instance.
        """
        pass
