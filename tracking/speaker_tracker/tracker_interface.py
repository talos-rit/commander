# tracker_interface.py
from abc import ABC, abstractmethod

class TrackerInterface(ABC):
    @abstractmethod
    def update(self, frame, bboxes):
        """
        Update the tracking using the given frame and list of bounding boxes.
        
        Args:
            frame: The current video frame.
            bboxes: A list of bounding boxes detected in the frame.
        
        Returns:
            The updated bounding box of the tracked speaker if tracking is successful,
            otherwise None.
        """
        pass

    @abstractmethod
    def set_speaker(self, bbox, speaker_color):
        """
        Set the initial tracking target using the provided bounding box and speaker color.
        
        Args:
            bbox: The bounding box [x1, y1, x2, y2] of the speaker.
            speaker_color: The color profile of the speaker.
        """
        pass
