import cv2

from assets import join_paths
from src.tracking.detector import ObjectModel

from ..types import BBox

MODEL_FILE = join_paths("haarcascade_frontalface_default.xml")


class BasicModel(ObjectModel):
    # The tracker class is responsible for capturing frames from the source and detecting faces in the frames
    def __init__(self):
        self.faceCascade = cv2.CascadeClassifier(MODEL_FILE)

    # Detect faces in the frame
    def detect_person(self, frame, inHeight=500, inWidth=0):
        frameGray, meta = self.resize_frame(
            frame, inHeight, inWidth, cvtColorCode=cv2.COLOR_BGR2GRAY
        )
        faces: list[BBox] = self.faceCascade.detectMultiScale(frameGray)  # pyright: ignore[reportAssignmentType]
        return [self.fix_bbox_scale(self.xywh_to_xyxy(xywh), meta) for xywh in faces]
