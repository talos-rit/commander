import cv2
import mediapipe as mp
import numpy as np
from loguru import logger
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

from src.tracking.detector import ObjectModel
from src.tracking.media_pipe.model_path import (
    path_efficientdet_lite0,
    path_pose_landmarker_lite,
)
from src.tracking.types import BBox

from .media_pipe_model import detection_result_to_xywh


class MediaPipePoseModel(ObjectModel):
    # The tracker class is responsible for capturing frames from the source and detecting people in the frames

    lost_counter = 0
    lost_threshold = 100
    speaker_color = None
    color_threshold = 15
    speaker_bbox: BBox | None = None

    def __init__(
        self,
    ):
        base_options = python.BaseOptions(model_asset_path=path_efficientdet_lite0)
        options = vision.ObjectDetectorOptions(
            base_options=base_options,
            score_threshold=0.5,
            category_allowlist=["person"],
        )
        self.object_detector = vision.ObjectDetector.create_from_options(options)

        pose_base_options = python.BaseOptions(
            model_asset_path=path_pose_landmarker_lite
        )
        pose_options = vision.PoseLandmarkerOptions(
            base_options=pose_base_options,
            # Additional options (e.g., running on CPU) can be specified here.
        )
        self.pose_detector = vision.PoseLandmarker.create_from_options(pose_options)

    # Detect people in the frame
    def detect_person(self, object_detector, frame, inHeight=500, inWidth=None):
        """
        Uses mediapipe to find all people in the frame and returns the bounding boxes of those people.
        """
        frameRGB, size = self.resize_frame(frame, inHeight, inWidth)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frameRGB)
        detection_result = object_detector.detect(mp_image)
        if not detection_result:
            return []

        bboxes = []
        for detection in detection_result.detections:
            xywh = detection_result_to_xywh(detection)
            bboxes.append(self.fix_bbox_scale(self.xywh_to_xyxy(xywh), size))
        return bboxes

    def is_x_pose(self, pose_landmarks):
        """
        Determine if the pose corresponds to an X formation.
        This example assumes that the pose landmarks are accessible by index.
        For MediaPipe Pose, typical landmark indices might be:
            - left_shoulder: 11
            - right_shoulder: 12
            - left_wrist: 15
            - right_wrist: 16
        Adjust these indices and thresholds as needed.
        """
        try:
            # Extract landmarks by index.
            left_shoulder = pose_landmarks[11]
            right_shoulder = pose_landmarks[12]
            left_wrist = pose_landmarks[15]
            right_wrist = pose_landmarks[16]
        except (IndexError, TypeError) as e:
            logger.error("Error extracting landmarks:", e)
            return False

        # Check that the left wrist is to the left of the left shoulder and
        # the right wrist is to the right of the right shoulder.
        if left_wrist.x < left_shoulder.x and right_wrist.x > right_shoulder.x:
            # Check that the vertical difference between wrists and shoulders is minimal.
            vertical_diff_left = abs(left_wrist.y - left_shoulder.y)
            vertical_diff_right = abs(right_wrist.y - right_shoulder.y)

            if vertical_diff_left < 0.1 and vertical_diff_right < 0.1:
                return True

        return False

    def get_cropped_box(self, bbox, frame):
        """
        Get cropped box for color tracking. Takes a much smaller portion of the bbox to get most dominant color.

        Parameters:
        - bbox - Current bounding box we are looking at
        - frame
        """
        x1, y1, x2, y2 = bbox

        # Default crop is just middle of box, where t-shirt is
        height = y2 - y1
        width = x2 - x1
        chest_start = y1 + int(height * 0.3)
        chest_end = y1 + int(height * 0.5)
        exclude_extra = x1 + int(width * 0.4)
        exclude_extra2 = x1 + int(width * 0.6)
        chest_crop = frame[chest_start:chest_end, exclude_extra:exclude_extra2]

        return chest_crop

    def get_dominant_color(self, image, quantize_level=16):
        """
        Finds the most dominant color in an image using color quantization.

        Parameters:
        - image: cropped region (H x W x 3)
        - quantize_level: smaller numbers = more grouping (e.g., 24, 32)

        Returns:
        - Dominant color as (B, G, R)
        """
        # Resize to reduce noise and speed up

        image = cv2.resize(image, (50, 50), interpolation=cv2.INTER_AREA)
        # image = cv2.GaussianBlur(image, (5, 5), 0)

        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        hue_channel = hsv[:, :, 0]  # Hue ranges from 0 to 179 in OpenCV

        # Quantize hue values
        quantized_hue = (hue_channel // quantize_level) * quantize_level

        # Flatten and find the most common hue bin
        unique_hues, counts = np.unique(quantized_hue.flatten(), return_counts=True)
        dominant_hue = unique_hues[np.argmax(counts)]

        return int(dominant_hue)
