import cv2

from assets import join_paths
from tracking.tracker import ObjectModel

MODEL_FILE = join_paths("haarcascade_frontalface_default.xml")


class BasicModel(ObjectModel):
    # The tracker class is responsible for capturing frames from the source and detecting faces in the frames
    def __init__(self):
        self.faceCascade = cv2.CascadeClassifier(MODEL_FILE)

    # Detect faces in the frame
    def detect_person(self, frame, inHeight=500, inWidth=0):
        frameOpenCVHaar = frame.copy()
        frameHeight = frameOpenCVHaar.shape[0]
        frameWidth = frameOpenCVHaar.shape[1]
        inWidth = inWidth or int((frameWidth / frameHeight) * inHeight)

        scaleHeight = frameHeight / inHeight
        scaleWidth = frameWidth / inWidth

        frameOpenCVHaarSmall = cv2.resize(frameOpenCVHaar, (inWidth, inHeight))
        frameGray = cv2.cvtColor(frameOpenCVHaarSmall, cv2.COLOR_BGR2GRAY)

        faces = self.faceCascade.detectMultiScale(frameGray)
        bboxes = []
        for x, y, w, h in faces:
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
