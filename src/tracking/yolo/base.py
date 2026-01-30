from enum import StrEnum
from os import path

import cv2
import numpy as np
import torch
from loguru import logger
from ultralytics import YOLO  # pyright: ignore[reportPrivateImportUsage]

from assets import join_paths
from src.tracking.tracker import ObjectModel


class YOLOModelSize(StrEnum):
    NANO = "nano"
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"
    XLARGE = "xlarge"

    @property
    def pt_file(self):
        return {
            YOLOModelSize.NANO: "yolo26n.pt",
            YOLOModelSize.SMALL: "yolo26s.pt",
            YOLOModelSize.MEDIUM: "yolo26m.pt",
            YOLOModelSize.LARGE: "yolo26l.pt",
            YOLOModelSize.XLARGE: "yolo26x.pt",
        }[self]

    @property
    def pose_pt_file(self):
        return {
            YOLOModelSize.NANO: "yolo26n-pose.pt",
            YOLOModelSize.SMALL: "yolo26s-pose.pt",
            YOLOModelSize.MEDIUM: "yolo26m-pose.pt",
            YOLOModelSize.LARGE: "yolo26l-pose.pt",
            YOLOModelSize.XLARGE: "yolo26x-pose.pt",
        }[self]


class YOLOBaseModel(ObjectModel):
    model_size: YOLOModelSize = YOLOModelSize.MEDIUM
    speaker_color: int | None = None
    color_threshold: int = 15
    lost_threshold: int = 300

    # The tracker class is responsible for capturing frames from the source and detecting people in the frames
    def __init__(
        self,
        _yolo_pt_dir=join_paths("yolo"),
        _pt_file: str | None = None,
        _pt_pose_file: str | None = None,
    ):
        self.speaker_bbox = None  # Shared reference. Only here to avoid pylint errors.
        self.device = "cuda:0" if torch.cuda.is_available() else "cpu"
        logger.info(f"Using YOLO model size: {self.model_size}, device: {self.device}")
        self.object_detector = YOLO(
            path.join(_yolo_pt_dir, _pt_file or self.model_size.pt_file)
        )
        self.pose_detector = YOLO(
            path.join(_yolo_pt_dir, _pt_pose_file or self.model_size.pose_pt_file)
        )
        self.lost_counter = 0

    # Detect people in the frame
    def detectPerson(self, object_detector, frame, inHeight=500, inWidth=None):
        inWidth = inWidth or int((frame.shape[1] / frame.shape[0]) * inHeight)
        frameOpenCV = frame.copy()
        frameHeight = frameOpenCV.shape[0]
        frameWidth = frameOpenCV.shape[1]

        frameSmall = cv2.resize(frameOpenCV, (inWidth, inHeight))
        frameRGB = cv2.cvtColor(frameSmall, cv2.COLOR_BGR2RGB)

        detection_result = object_detector(
            frameRGB, classes=0, verbose=False, imgsz=(576, 320), device=self.device
        )
        # print(detection_result)
        if not detection_result:
            return []

        bboxes = []
        for xyxy in detection_result[0].boxes.xyxyn:
            x1 = int(xyxy[0] * frameWidth)
            y1 = int(xyxy[1] * frameHeight)
            x2 = int(xyxy[2] * frameWidth)
            y2 = int(xyxy[3] * frameHeight)
            bboxes.append((x1, y1, x2, y2))
        # for i, detection in enumerate(detection_result):
        #     xyxy = detection.boxes.xyxyn
        #     x1 = int(xyxy[i][0] * frameWidth)
        #     y1 = int(xyxy[i][1] * frameHeight)
        #     x2 = int(xyxy[i][2] * frameWidth)
        #     y2 = int(xyxy[i][3] * frameHeight)
        #     bboxes.append((x1, y1, x2, y2))
        # print(bboxes)

        return bboxes

    def is_x_pose_yolo(self, person_keypoints, threshold=0.1):
        """
        Given the keypoints for one person from a YOLOv8 pose detection,
        check if they are in the "X-Pose."

        'person_keypoints' is expected to be either:
        - shape (17, 2) -> (x, y)
        - shape (17, 3) -> (x, y, confidence)
        Indices: left_shoulder=5, right_shoulder=6, left_wrist=9, right_wrist=10 in COCO format.

        threshold: maximum vertical difference (normalized) allowed between wrists and shoulders.
        """

        # Ensure we have enough keypoints
        # print(person_keypoints[0])

        if person_keypoints.shape[1] < 11:
            return False

        kp_xy = person_keypoints.xyn[0]

        # Now kp_xy[i, 0] is x, kp_xy[i, 1] is y for keypoint i
        # For example, let's get the left shoulder (index 5) and right shoulder (index 6).

        x_ls = float(kp_xy[5, 0])
        y_ls = float(kp_xy[5, 1])
        x_rs = float(kp_xy[6, 0])
        # y_rs = float(kp_xy[6, 1])
        x_lw = float(kp_xy[10, 0])
        y_lw = float(kp_xy[10, 1])
        x_rw = float(kp_xy[11, 0])
        # y_rw = float(kp_xy[11, 1])
        # print("XLS" + str(x_ls))

        # 1) Check horizontal arrangement:
        # left wrist < left shoulder AND right wrist > right shoulder
        # 2) Check vertical difference:
        # |left wrist y - left shoulder y| < threshold
        return x_lw < x_ls and x_rw > x_rs and abs(y_lw - y_ls) < threshold

    # Capture a frame from the source and detect faces in the frame
    def detect_person(self, frame):
        bboxes = self.detectPerson(self.object_detector, frame)

        if self.speaker_bbox is None:
            # If no speaker is locked in yet, look for the X pose.
            # We assume only one person is in frame when the X pose is made.
            for box in bboxes:
                x1, y1, x2, y2 = box
                cropped = frame[y1:y2, x1:x2]
                if cropped.size == 0:
                    continue
                cropped = cropped.astype("uint8")
                # Run pose detection on the cropped image.
                pose_result = self.pose_detector(
                    cropped, verbose=False, device=self.device
                )
                if len(pose_result) == 0:
                    continue
                # "results[0]" is the prediction for this single image/crop
                result = pose_result[0]
                if result.keypoints is not None and self.is_x_pose_yolo(
                    result.keypoints
                ):
                    self.speaker_bbox = box
                    smaller_box = self.getCroppedBox(box, frame)
                    color = self.get_dominant_color(smaller_box)
                    self.speaker_color = color
                    logger.info(f"Speaker detected with X pose: {self.speaker_bbox}")
                    return [self.speaker_bbox]

            # While speaker not yet locked, return all detected bounding boxes.
            # This will just have the director track whichever it sees first. If there is only one person in frame this is fine
            return bboxes

        # If frame is empty after detecting a speaker, increment the lost speaker counter
        self.lost_counter += 1
        if len(bboxes) > 0:
            # Speaker is already locked. Find the current detection that is closest to the stored speaker bbox.
            best_bbox = None
            best_candidate_color = None

            for bbox in bboxes:
                x1, y1, x2, y2 = bbox
                smaller_box = self.getCroppedBox(bbox, frame)
                color = self.get_dominant_color(smaller_box)
                # Compute the Euclidean distance between the candidate color and the stored speaker color.
                color_diff = abs((self.speaker_color or 0) - color)

                if color_diff < self.color_threshold:
                    best_bbox = bbox
                    best_candidate_color = color

            if best_bbox is not None:
                # Found a candidate has similar color.
                self.speaker_bbox = best_bbox
                self.speaker_color = best_candidate_color
                self.lost_counter = 0

        if self.lost_counter >= self.lost_threshold:
            logger.warning(
                "Speaker lost for too many frames. Resetting single speaker."
            )
            self.speaker_bbox = None
            self.speaker_color = None
            self.lost_counter = 0

        return [self.speaker_bbox] if self.speaker_bbox is not None else []

    def getCroppedBox(self, bbox, frame):
        x1, y1, x2, y2 = bbox

        # Default crop is just middle of box
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
