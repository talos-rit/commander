from abc import ABC, abstractmethod

# Abstract class for tracking
class Tracker(ABC):

    # Capture a frame from the source
    @abstractmethod
    def capture_frame(self):
        pass