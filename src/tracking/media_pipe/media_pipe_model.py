import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

from src.tracking.detector import ObjectModel
from src.tracking.media_pipe.model_path import path_efficientdet_lite0
from src.tracking.types import BBox


class MediaPipeModel(ObjectModel):
    inHeight = 500
    inWidth = None

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

    def detect_person(self, frame) -> list[BBox]:
        frameRGB, size = self.resize_frame(frame, self.inHeight, self.inWidth)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frameRGB)
        detection_result = self.object_detector.detect(mp_image)
        bboxes: list[BBox] = []
        if detection_result:
            for detection in detection_result.detections:
                bboxC = detection.bounding_box
                x1 = bboxC.origin_x
                y1 = bboxC.origin_y
                x2 = bboxC.origin_x + bboxC.width
                y2 = bboxC.origin_y + bboxC.height
                bboxes.append(self.fix_bbox_scale((x1, y1, x2, y2), size))
        return bboxes
