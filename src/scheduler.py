from abc import ABC, abstractmethod


class IterativeTask(ABC):
    is_running = True
    scheduler: "Scheduler"

    @abstractmethod
    def cancel(self):
        raise NotImplementedError

    @abstractmethod
    def set_interval(self, ms: int):
        raise NotImplementedError

    @abstractmethod
    def get_interval(self) -> int:
        raise NotImplementedError


class Scheduler(ABC):
    @abstractmethod
    def set_timeout(self, ms, func, *args):
        """Set a timeout to call func after ms milliseconds."""
        raise NotImplementedError

    @abstractmethod
    def set_interval(self, ms, func, *args) -> IterativeTask:
        """
        Calls func every ms milliseconds.
        Return an IterativeTask instance.
        """
        raise NotImplementedError
