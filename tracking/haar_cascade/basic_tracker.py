from tracking.tracker import Tracker
import cv2
import yaml

class BasicTracker(Tracker):

    # The tracker class is responsible for capturing frames from the source and detecting faces in the frames
    def __init__(self, source : str, config_path):
        self.source = source

        self.faceCascade = cv2.CascadeClassifier("tracking/haar_cascade/haarcascade_frontalface_default.xml")

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

    # Detect faces in the frame
    def detectFace(self, faceCascade, frame, inHeight=500, inWidth=0):
        frameOpenCVHaar = frame.copy()
        frameHeight = frameOpenCVHaar.shape[0]
        frameWidth = frameOpenCVHaar.shape[1]
        if not inWidth:
            inWidth = int((frameWidth / frameHeight) * inHeight)

        scaleHeight = frameHeight / inHeight
        scaleWidth = frameWidth / inWidth

        frameOpenCVHaarSmall = cv2.resize(frameOpenCVHaar, (inWidth, inHeight))
        frameGray = cv2.cvtColor(frameOpenCVHaarSmall, cv2.COLOR_BGR2GRAY)

        faces = faceCascade.detectMultiScale(frameGray)
        bboxes = []
        for (x, y, w, h) in faces:
            x1 = x
            y1 = y
            x2 = x + w
            y2 = y + h
            cvRect = [
                int(x1 * scaleWidth),
                int(y1 * scaleHeight),
                int(x2 * scaleWidth),
                int(y2 * scaleHeight),
            ]
            bboxes.append(cvRect)
        return bboxes
    
    # Capture a frame from the source and detect faces in the frame
    def capture_frame(self):

        hasFrame, frame = self.cap.read()
        if not hasFrame:
            return None, None

        bboxes = self.detectFace(self.faceCascade, frame)
        
        return bboxes, frame