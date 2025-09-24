import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

from tracking.tracker import Tracker
from utils import get_file_path


class MediaPipeTracker(Tracker):
    # The tracker class is responsible for capturing frames from the source and detecting people in the frames
    def __init__(self, source: str, config_path, video_label):
        self.speaker_bbox = None  # Shared reference. Only here to avoid pylint errors.
        super().__init__(source, config_path, video_label)

        base_options = python.BaseOptions(
            model_asset_path=get_file_path(
                "tracking/media_pipe/efficientdet_lite0.tflite"
            )
        )
        options = vision.ObjectDetectorOptions(
            base_options=base_options,
            score_threshold=0.5,
            category_allowlist=["person"],
        )
        self.object_detector = vision.ObjectDetector.create_from_options(options)

        # Open the video source
        if self.source:
            self.cap = cv2.VideoCapture(self.source)
        else:
            config = self.load_config(config_path)
            camera_index = config["camera_index"]
            self.cap = cv2.VideoCapture(camera_index)

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

        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frameRGB)
        detection_result = object_detector.detect(mp_image)
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

    # Capture a frame from the source and detect faces in the frame
    def capture_frame(self, is_interface_running):
        hasFrame, frame = self.cap.read()
        if not hasFrame:
            return None, None
        # frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)

        bboxes = self.detectPerson(self.object_detector, frame)

        self.draw_visuals(bboxes, frame, is_interface_running)

        self.change_video_frame(frame, is_interface_running)

        return bboxes, frame
