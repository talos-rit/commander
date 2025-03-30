from tracking.tracker import Tracker
from ultralytics import YOLO
import cv2
import yaml
import numpy as np
from tracking.identifier.x_pose_identifier import XPoseIdentifier
from tracking.speaker_tracker.color_tracker import ColorTracker

class YOLOTracker(Tracker):
    def __init__(self, source: str, config_path):
        self.source = source

        # Initialize YOLO object detector.
        self.object_detector = YOLO("yolo11m.pt")  # Ensure this model supports pose detection on GPU.

        # Instantiate the identifier using YOLO (GPU) instead of MediaPipe.
        self.identifier = XPoseIdentifier(self.object_detector)
        self.tracker = ColorTracker(lost_threshold=100, color_threshold=15)

        # Open the video source.
        if self.source:
            self.cap = cv2.VideoCapture(self.source)
        else:
            config = self.load_config(config_path)
            camera_index = config['camera_index']
            self.cap = cv2.VideoCapture(camera_index)

    def load_config(self, config_path):
        with open(config_path, 'r') as file:
            return yaml.safe_load(file)

    def detectPerson(self, object_detector, frame, inHeight=500, inWidth=0):
        frameOpenCV = frame.copy()
        frameHeight = frameOpenCV.shape[0]
        frameWidth = frameOpenCV.shape[1]

        if not inWidth:
            inWidth = int((frameWidth / frameHeight) * inHeight)

        scaleHeight = frameHeight / inHeight
        scaleWidth = frameWidth / inWidth

        frameSmall = cv2.resize(frameOpenCV, (inWidth, inHeight))
        frameRGB = cv2.cvtColor(frameSmall, cv2.COLOR_BGR2RGB)

        # Run YOLO for object detection on GPU.
        detection_result = object_detector(
            frameRGB, classes=0, verbose=False, imgsz=(576, 320), device='0'
        )
        bboxes = []
        if detection_result:
            for detection in detection_result:
                xyxy = detection.boxes.xyxyn
                print(xyxy)
                for box in xyxy:
                    x1 = int(box[0] * frameWidth)
                    y1 = int(box[1] * frameHeight)
                    x2 = int(box[2] * frameWidth)
                    y2 = int(box[3] * frameHeight)
                bboxes.append((x1, y1, x2, y2))
            print("DONE")
        return bboxes

    def capture_frame(self):
        hasFrame, frame = self.cap.read()
        if not hasFrame:
            return None, None

        bboxes = self.detectPerson(self.object_detector, frame)

        # If no speaker is locked, use the XPoseIdentifier to search for one.
        if self.tracker.speaker_bbox is None:
            for bbox in bboxes:
                detected, speaker_color = self.identifier.identify(frame, bbox)
                if detected:
                    self.tracker.set_speaker(bbox, speaker_color)
                    print("Speaker detected with X pose:", bbox)
                    return [bbox], frame
            return bboxes, frame
        else:
            # Update tracking based on current detections.
            updated_bbox = self.tracker.update(frame, bboxes)
            return ([updated_bbox] if updated_bbox is not None else []), frame
