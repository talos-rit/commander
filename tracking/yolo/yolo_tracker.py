import math
import os

import cv2
import mediapipe as mp
import numpy as np
import torch
import yaml
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
from ultralytics import YOLO

from tracking.tracker import Tracker

# TODO: Move this into a config file
DEFAULT_YOLO_MODEL_DIR = os.path.join(os.path.dirname(__file__), "yolo-pt")


def create_pt_file_path(file_name, _dir=DEFAULT_YOLO_MODEL_DIR):
    return os.path.join(_dir, file_name)


class YOLOTracker(Tracker):
    # The tracker class is responsible for capturing frames from the source and detecting people in the frames
    def __init__(
        self, source: str, config_path, video_label, _yolo_pt_dir=DEFAULT_YOLO_MODEL_DIR
    ):
        self.speaker_bbox = None  # Shared reference. Only here to avoid pylint errors.
        super().__init__(source, config_path, video_label)

        self.device = "cuda:0" if torch.cuda.is_available() else "cpu"
        self.object_detector = YOLO(
            create_pt_file_path("yolo11m.pt", _dir=_yolo_pt_dir)
        )

        self.pose_detector = YOLO(
            create_pt_file_path("yolo11m-pose.pt", _dir=_yolo_pt_dir)
        )

        self.lost_counter = 0
        self.lost_threshold = 300

        self.speaker_color = None
        self.color_threshold = 15

    # Detect people in the frame
    def detectPerson(self, object_detector, frame, inHeight=500, inWidth=0):
        frameOpenCV = frame.copy()
        frameHeight = frameOpenCV.shape[0]
        frameWidth = frameOpenCV.shape[1]

        if not inWidth:
            inWidth = int((frameWidth / frameHeight) * inHeight)

        frameSmall = cv2.resize(frameOpenCV, (inWidth, inHeight))
        frameRGB = cv2.cvtColor(frameSmall, cv2.COLOR_BGR2RGB)

        detection_result = object_detector(
            frameRGB, classes=0, verbose=False, imgsz=(576, 320), device=self.device
        )
        # print(detection_result)
        bboxes = []
        if detection_result:
            # print(detection_result[0].boxes.xyxyn)
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
            print("shape")
            print(person_keypoints.shape[0])
            return False

        kp_xy = person_keypoints.xyn[0]

        # Now kp_xy[i, 0] is x, kp_xy[i, 1] is y for keypoint i
        # For example, let's get the left shoulder (index 5) and right shoulder (index 6).

        x_ls = float(kp_xy[5, 0])
        y_ls = float(kp_xy[5, 1])
        x_rs = float(kp_xy[6, 0])
        y_rs = float(kp_xy[6, 1])
        x_lw = float(kp_xy[10, 0])
        y_lw = float(kp_xy[10, 1])
        x_rw = float(kp_xy[11, 0])
        y_rw = float(kp_xy[11, 1])
        # print("XLS" + str(x_ls))

        # 1) Check horizontal arrangement: left wrist < left shoulder AND right wrist > right shoulder
        if x_lw < x_ls and x_rw > x_rs:
            # 2) Check vertical difference
            vertical_diff_left = abs(y_lw - y_ls)
            # print(vertical_diff_left)

            if vertical_diff_left < threshold:
                return True

        return False

    def compute_center(self, bbox):
        """Compute the center of a bounding box."""
        x1, y1, x2, y2 = bbox
        return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)

    def bbox_distance(self, bbox1, bbox2):
        """Compute the distance between the centers of two bounding boxes."""
        cx1, cy1 = self.compute_center(bbox1)
        cx2, cy2 = self.compute_center(bbox2)
        return math.sqrt((cx1 - cx2) ** 2 + (cy1 - cy2) ** 2)

    # Capture a frame from the source and detect faces in the frame
    def capture_frame(self, is_interface_running):
        hasFrame, frame = self.cap.read()
        if not hasFrame:
            return None, None
        # frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
        bboxes = self.detectPerson(self.object_detector, frame)

        self.draw_visuals(bboxes, frame, is_interface_running)

        self.change_video_frame(frame, is_interface_running)

        if self.speaker_bbox is None:
            # If no speaker is locked in yet, look for the X pose.
            # We assume only one person is in frame when the X pose is made.
            for box in bboxes:
                bbox = box
                x1, y1, x2, y2 = bbox
                cropped = frame[y1:y2, x1:x2]
                if cropped.size > 0:
                    cropped = cropped.astype("uint8")
                    # Run pose detection on the cropped image.
                    pose_result = self.pose_detector(
                        cropped, verbose=False, device=self.device
                    )
                    if len(pose_result) > 0:
                        # "results[0]" is the prediction for this single image/crop
                        result = pose_result[0]
                        if result.keypoints is not None:
                            if self.is_x_pose_yolo(result.keypoints):
                                self.speaker_bbox = box
                                smaller_box = self.getCroppedBox(box, frame)
                                color = self.get_dominant_color(smaller_box)
                                self.speaker_color = color
                                print(
                                    "Speaker detected with X pose:", self.speaker_bbox
                                )
                                return [self.speaker_bbox], frame

            # While speaker not yet locked, return all detected bounding boxes.
            # This will just have the director track whichever it sees first. If there is only one person in frame this is fine
            return bboxes, frame

        # If frame is empty after detecting a speaker, increment the lost speaker counter
        if len(bboxes) == 0:
            # No detections
            self.lost_counter += 1
        else:
            # Speaker is already locked. Find the current detection that is closest to the stored speaker bbox.
            best_bbox = None
            best_candidate_color = None

            for bbox in bboxes:
                x1, y1, x2, y2 = bbox
                smaller_box = self.getCroppedBox(bbox, frame)
                color = self.get_dominant_color(smaller_box)
                # Compute the Euclidean distance between the candidate color and the stored speaker color.
                color_diff = abs(self.speaker_color - color)

                if color_diff < self.color_threshold:
                    best_bbox = bbox
                    best_candidate_color = color

            if best_bbox is not None:
                # Found a candidate has similar color.
                self.speaker_bbox = best_bbox
                self.speaker_color = best_candidate_color
                self.lost_counter = 0
            else:
                self.lost_counter += 1

        if self.lost_counter >= self.lost_threshold:
            print("Speaker lost for too many frames. Resetting single speaker.")
            self.speaker_bbox = None
            self.speaker_color = None
            self.lost_counter = 0

        return ([self.speaker_bbox] if self.speaker_bbox is not None else []), frame

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
