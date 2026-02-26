import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

from src.tracking.detector import ObjectModel
from src.tracking.media_pipe.model_path import path_efficientdet_lite0


class MediaPipeModel(ObjectModel):
    inHeight = 500
    inWidth = 0

    # The tracker class is responsible for capturing frames from the source and detecting people in the frames
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

    # Detect people in the frame
    def detect_person(self, frame):
        frameOpenCV = frame.copy()
        frameHeight = frameOpenCV.shape[0]
        frameWidth = frameOpenCV.shape[1]

        if not self.inWidth:
            self.inWidth = int((frameWidth / frameHeight) * self.inHeight)

        scaleHeight = frameHeight / self.inHeight
        scaleWidth = frameWidth / self.inWidth

        frameSmall = cv2.resize(frameOpenCV, (self.inWidth, self.inHeight))
        frameRGB = cv2.cvtColor(frameSmall, cv2.COLOR_BGR2RGB)

        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frameRGB)
        detection_result = self.object_detector.detect(mp_image)
        bboxes = []
        if detection_result:
            for detection in detection_result.detections:
                # print(detection)
                bboxC = detection.bounding_box

                x1 = bboxC.origin_x
                y1 = bboxC.origin_y
                x2 = bboxC.origin_x + bboxC.width
                y2 = bboxC.origin_y + bboxC.height

                # Scale bounding box back to original frame size
                cvRect = [
                    int(x1 * scaleWidth),
                    int(y1 * scaleHeight),
                    int(x2 * scaleWidth),
                    int(y2 * scaleHeight),
                ]
                bboxes.append(cvRect)
        return bboxes
