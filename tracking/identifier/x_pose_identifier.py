# speaker_identifier.py
import cv2
import numpy as np
from tracking.identifier.identifier_interface import IdentifierInterface

class XPoseIdentifier:
    def __init__(self, yolo_model):
        self.yolo_model = yolo_model

    def is_x_pose(self, keypoints):
        """
        Determine if the keypoints correspond to an X formation.
        Assumes keypoints is a list where each element is [x, y, confidence]
        and the indices are:
            - left_shoulder: 11
            - right_shoulder: 12
            - left_wrist: 15
            - right_wrist: 16
        """
        try:
            left_shoulder = keypoints[11]
            right_shoulder = keypoints[12]
            left_wrist = keypoints[15]
            right_wrist = keypoints[16]
        except IndexError:
            return False

        # Check if left wrist is left of left shoulder and right wrist is right of right shoulder.
        if left_wrist[0] < left_shoulder[0] and right_wrist[0] > right_shoulder[0]:
            vertical_diff_left = abs(left_wrist[1] - left_shoulder[1])
            vertical_diff_right = abs(right_wrist[1] - right_shoulder[1])
            if vertical_diff_left < 0.1 and vertical_diff_right < 0.1:
                return True
        return False

    def identify(self, frame, bbox):
        """
        Crop the image to the given bbox and run YOLO (in pose mode)
        on GPU to detect keypoints. If the detected keypoints represent an X pose,
        return (True, speaker_color) where speaker_color is computed from the crop.
        """
        x1, y1, x2, y2 = bbox
        cropped = frame[y1:y2, x1:x2]
        if cropped.size == 0:
            return False, None

        # Run YOLO inference on the cropped image using GPU.
        # Note: This assumes the provided YOLO model is set up for pose detection.
        results = self.yolo_model(cropped, device='gpu')
        if results and len(results) > 0:
            detection = results[0]
            # Assume that a valid detection has an attribute 'keypoints'
            if hasattr(detection, "keypoints") and detection.keypoints is not None:
                keypoints = detection.keypoints  # Expected format: list of [x, y, confidence]
                if self.is_x_pose(keypoints):
                    speaker_color = np.mean(cropped, axis=(0, 1))
                    return True, speaker_color

        return False, None
