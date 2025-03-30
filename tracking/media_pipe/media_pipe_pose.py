# mediapipe_pose.py
import math
import cv2
import yaml
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
from tracking.tracker import Tracker
from tracking.identifier.x_pose_identifier import XPoseIdentifier
from tracking.speaker_tracker.color_tracker import ColorTracker

class MediaPipePose(Tracker):
    def __init__(self, source: str, config_path):
        self.source = source

        base_options = python.BaseOptions(model_asset_path="tracking/media_pipe/efficientdet_lite0.tflite")
        options = vision.ObjectDetectorOptions(
            base_options=base_options, score_threshold=0.5, category_allowlist=["person"]
        )
        self.object_detector = vision.ObjectDetector.create_from_options(options)

        pose_base_options = python.BaseOptions(model_asset_path="tracking/media_pipe/pose_landmarker_lite.task")
        pose_options = vision.PoseLandmarkerOptions(
            base_options=pose_base_options,
        )
        self.pose_detector = vision.PoseLandmarker.create_from_options(pose_options)

        # Use the interface implementations.
        self.identifier = XPoseIdentifier(self.pose_detector)
        self.tracker = ColorTracker(lost_threshold=100, color_threshold=15)

        try:
            if self.source:
                self.cap = cv2.VideoCapture(self.source)
            else:
                config = self.load_config(config_path)
                camera_index = config['camera_index']
                self.cap = cv2.VideoCapture(camera_index)
        except Exception as e:
            print("Error opening video source: ", e)

    def load_config(self, config_path):
        with open(config_path, 'r') as file:
            return yaml.safe_load(file)

    def detectPerson(self, object_detector, frame, inHeight=500, inWidth=0):
        frameOpenCV = frame.copy()
        frameHeight, frameWidth = frameOpenCV.shape[:2]
        if not inWidth:
            inWidth = int((frameWidth / frameHeight) * inHeight)
        scaleHeight = frameHeight / inHeight
        scaleWidth = frameWidth / inWidth

        frameSmall = cv2.resize(frameOpenCV, (inWidth, inHeight))
        frameRGB = cv2.cvtColor(frameSmall, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frameRGB)
        detection_result = object_detector.detect(mp_image)
        bboxes = []
        if detection_result:
            for detection in detection_result.detections:
                bboxC = detection.bounding_box
                x1 = bboxC.origin_x
                y1 = bboxC.origin_y
                x2 = bboxC.origin_x + bboxC.width
                y2 = bboxC.origin_y + bboxC.height
                cvRect = [
                    int(x1 * scaleWidth),
                    int(y1 * scaleHeight),
                    int(x2 * scaleWidth),
                    int(y2 * scaleHeight)
                ]
                bboxes.append(cvRect)
        return bboxes

    def capture_frame(self):
        hasFrame, frame = self.cap.read()
        if not hasFrame:
            return None, None

        bboxes = self.detectPerson(self.object_detector, frame)

        if self.tracker.speaker_bbox is None:
            for bbox in bboxes:
                detected, speaker_color = self.identifier.identify(frame, bbox)
                if detected:
                    self.tracker.set_speaker(bbox, speaker_color)
                    print("Speaker detected with X pose:", bbox)
                    return [bbox], frame
            return bboxes, frame
        else:
            updated_bbox = self.tracker.update(frame, bboxes)
            return ([updated_bbox] if updated_bbox is not None else []), frame
