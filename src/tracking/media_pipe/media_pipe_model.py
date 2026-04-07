import mediapipe as mp
from mediapipe.tasks.python import BaseOptions, vision

from src.tracking.detector import ObjectModel
from src.tracking.media_pipe.model_path import path_efficientdet_lite0
from src.tracking.types import BBox


def detection_result_to_xywh(detection_result) -> BBox:
    bboxC = detection_result.bounding_box
    return (
        bboxC.origin_x,
        bboxC.origin_y,
        bboxC.width,
        bboxC.height,
    )


class MediaPipeModel(ObjectModel):
    inHeight = 500
    inWidth = None

    # The tracker class is responsible for capturing frames from the source and detecting people in the frames
    def __init__(
        self,
    ):
        base_options = BaseOptions(model_asset_path=path_efficientdet_lite0)
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
        bboxes = []
        if detection_result:
            for detection in detection_result.detections:
                xywh = detection_result_to_xywh(detection)
                bboxes.append(self.fix_bbox_scale(self.xywh_to_xyxy(xywh), size))
        return bboxes
