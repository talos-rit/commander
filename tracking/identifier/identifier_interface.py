# identifier_interface.py
from abc import ABC, abstractmethod

class IdentifierInterface(ABC):
    @abstractmethod
    def identify(self, frame, bbox):
        """
        Analyze the given frame and bounding box to determine if it matches
        the primary speaker criteria.
        
        Args:
            frame: The current video frame.
            bbox: A bounding box [x1, y1, x2, y2] representing a detected person.
        
        Returns:
            A tuple (detected: bool, speaker_color: any) where 'detected' is True
            if the speaker is identified and 'speaker_color' is the computed color profile.
        """
        pass
