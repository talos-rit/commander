from tracking.tracker import Tracker
from ultralytics import YOLO
import cv2
import yaml


class YOLOTracker(Tracker):

    # The tracker class is responsible for capturing frames from the source and detecting people in the frames
    def __init__(self, source : str, config_path):
        self.source = source

        self.object_detector = YOLO("yolo11m.pt")

        # Open the video source
        if self.source:
            self.cap = cv2.VideoCapture(self.source)
        else:
            config = self.load_config(config_path)
            camera_index = config['camera_index']
            self.cap = cv2.VideoCapture(camera_index)

    def load_config(self, config_path):
        with open(config_path, 'r') as file:
            return yaml.safe_load(file)

    # Detect people in the frame
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

        detection_result = object_detector(frameRGB, classes=0, verbose=False, imgsz=(576, 320), device='cpu')
        print(detection_result)
        bboxes = []
        if detection_result:
            # print(detection_result[0].boxes)
            for detection in detection_result:
                xyxy = detection.boxes.xyxyn
                #print(detection.boxes.xyxy)
                x1 = int(xyxy[0][0] * frameWidth)
                y1 = int(xyxy[0][1] * frameHeight)
                x2 = int(xyxy[0][2] * frameWidth)
                y2 = int(xyxy[0][3] * frameHeight)
                bboxes.append((x1, y1, x2, y2))

        return bboxes
    
    # Capture a frame from the source and detect faces in the frame
    def capture_frame(self):

        hasFrame, frame = self.cap.read()
        if not hasFrame:
            return None, None

        bboxes = self.detectPerson(self.object_detector, frame)
        

        return bboxes, frame
