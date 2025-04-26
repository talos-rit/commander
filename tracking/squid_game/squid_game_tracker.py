from tracking.tracker import Tracker
from ultralytics import YOLO
import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
import math
import yaml
import torch


class SquidGameTracker(Tracker):

    # The tracker class is responsible for capturing frames from the source and detecting people in the frames
    def __init__(self, source : str, config_path, video_label):
        self.speaker_bbox = None  #Shared reference. Only here to avoid pylint errors.
        super().__init__(source, config_path, video_label)

        self.device = "cuda:0" if torch.cuda.is_available() else "cpu"
        self.object_detector = YOLO("yolo11m.pt")

    # Detect people in the frame
    def detectPerson(self, object_detector, frame, inHeight=500, inWidth=0):
        frameOpenCV = frame.copy()
        frameHeight = frameOpenCV.shape[0]
        frameWidth = frameOpenCV.shape[1]

        if not inWidth:
            inWidth = int((frameWidth / frameHeight) * inHeight)

        frameSmall = cv2.resize(frameOpenCV, (inWidth, inHeight))
        frameRGB = cv2.cvtColor(frameSmall, cv2.COLOR_BGR2RGB)

        detection_result = object_detector(frameRGB, classes=0, verbose=False, imgsz=(576, 320), device=self.device)
        bboxes = []
        if detection_result:
            for xyxy in detection_result[0].boxes.xyxyn:
                x1 = int(xyxy[0] * frameWidth)
                y1 = int(xyxy[1] * frameHeight)
                x2 = int(xyxy[2] * frameWidth)
                y2 = int(xyxy[3] * frameHeight)
                bboxes.append((x1, y1, x2, y2))
            
        return bboxes 

    def capture_frame(self, is_interface_running):

        hasFrame, frame = self.cap.read()
        if not hasFrame:
            return None, None
        #frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)

        bboxes = self.detectPerson(self.object_detector, frame)
        
        return bboxes, frame