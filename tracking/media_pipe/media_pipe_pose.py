import math
import cv2
import yaml
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
from tracking.tracker import Tracker


class MediaPipePose(Tracker):

    # The tracker class is responsible for capturing frames from the source and detecting people in the frames
    def __init__(self, source : str, config_path):
        self.source = source

        base_options = python.BaseOptions(model_asset_path="tracking/media_pipe/efficientdet_lite0.tflite")
        options = vision.ObjectDetectorOptions(base_options=base_options, score_threshold=0.5, category_allowlist=["person"])
        self.object_detector = vision.ObjectDetector.create_from_options(options)

        pose_base_options = python.BaseOptions(model_asset_path="tracking/media_pipe/pose_landmarker_lite.task")
        pose_options = vision.PoseLandmarkerOptions(
            base_options=pose_base_options,
            # Additional options (e.g., running on CPU) can be specified here.
        )
        self.pose_detector = vision.PoseLandmarker.create_from_options(pose_options)

        # Open the video source
        if self.source:
            self.cap = cv2.VideoCapture(self.source)  
        else:
            config = self.load_config(config_path)
            camera_index = config['camera_index']
            self.cap = cv2.VideoCapture(camera_index)

        self.speaker_bbox = None
        self.lost_counter = 0
        self.lost_threshold = 10

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

        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frameRGB)
        detection_result = object_detector.detect(mp_image)
        bboxes = []
        if detection_result:
            for detection in detection_result.detections:
                #print(detection)
                bboxC = detection.bounding_box
                #print(bboxC)

                x1 = bboxC.origin_x
                y1 = bboxC.origin_y
                x2 = bboxC.origin_x + bboxC.width
                y2 = bboxC.origin_y + bboxC.height

                # Scale bounding box back to original frame size
                cvRect = [
                    int(x1 * scaleWidth),
                    int(y1 * scaleHeight),
                    int(x2 * scaleWidth),
                    int(y2 * scaleHeight)
                ]
                bboxes.append(cvRect)
        return bboxes
    
    def is_x_pose(self, pose_landmarks):
        """
        Determine if the pose corresponds to an X formation.
        This example assumes that the pose landmarks are accessible by index.
        For MediaPipe Pose, typical landmark indices might be:
            - left_shoulder: 11
            - right_shoulder: 12
            - left_wrist: 15
            - right_wrist: 16
        Adjust these indices and thresholds as needed.
        """
        try:
            # Extract landmarks by index.
            left_shoulder = pose_landmarks[11]
            right_shoulder = pose_landmarks[12]
            left_wrist = pose_landmarks[15]
            right_wrist = pose_landmarks[16]
        except (IndexError, TypeError) as e:
            print("Error extracting landmarks:", e)
            return False

        # Check that the left wrist is to the left of the left shoulder and
        # the right wrist is to the right of the right shoulder.
        if left_wrist.x < left_shoulder.x and right_wrist.x > right_shoulder.x:
            # Check that the vertical difference between wrists and shoulders is minimal.
            vertical_diff_left = abs(left_wrist.y - left_shoulder.y)
            vertical_diff_right = abs(right_wrist.y - right_shoulder.y)

            if vertical_diff_left < 0.1 and vertical_diff_right < 0.1:
                return True
            
        return False

    def compute_center(self, bbox):
        """Compute the center of a bounding box."""
        x1, y1, x2, y2 = bbox
        return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)

    def bbox_distance(self, bbox1, bbox2):
        """Compute the distance between the centers of two bounding boxes."""
        cx1, cy1 = self.compute_center(bbox1)
        cx2, cy2 = self.compute_center(bbox2)
        return math.sqrt((cx1 - cx2) ** 2 + (cy1 - cy2) ** 2)

    # Capture a frame from the source and detect faces in the frame
    def capture_frame(self):

        hasFrame, frame = self.cap.read()
        if not hasFrame:
            return None, None
        #Use this rotate if the mp4 is showing up incorrectly
        frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
        bboxes = self.detectPerson(self.object_detector, frame)

        if len(bboxes) < 1:
            #This is for when there is no person in frame, we still want the video to show
            cv2.imshow('Object Detection', frame)

        if self.speaker_bbox is None:
            # If no speaker is locked in yet, look for the X pose.
            # We assume only one person is in frame when the X pose is made.
            if len(bboxes) == 1:
                bbox = bboxes[0]
                x1, y1, x2, y2 = bbox
                cropped = frame[y1:y2, x1:x2]
                if cropped.size > 0:
                    cropped_rgb = cv2.cvtColor(cropped, cv2.COLOR_BGR2RGB)
                    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=cropped_rgb)
                    # Run pose detection on the cropped image.
                    pose_result = self.pose_detector.detect(mp_image)
                    if pose_result and pose_result.pose_landmarks:
                        landmarks = pose_result.pose_landmarks[0]
   
                        # Check for the X formation.
                        if self.is_x_pose(landmarks):
                            self.speaker_bbox = bbox
                            print("Speaker detected with X pose:", self.speaker_bbox)

            # While speaker not yet locked, return all detected bounding boxes.
            # We want to return them because we still want to draw the bounding boxes in the director
            # We may need to add something to director to ensure it doesn't send commands 
            # Or we can just leave it to operate on first bounding box while there is no speaker
            return bboxes, frame
        else:
            # The way I decided to do this is to find the bounding box closest to the previously stored one
            # This is a makeshift way of ensuring we are getting the same target
            # Currently this is a struggle with people walking in front of the target

            if len(bboxes) == 0:
                # No detections
                self.lost_counter += 1
            else:
                # Speaker is already locked. Find the current detection that is closest to the stored speaker bbox.
                min_distance = float('inf')
                best_bbox = None
                for bbox in bboxes:
                    dist = self.bbox_distance(bbox, self.speaker_bbox)
                    if dist < min_distance:
                        min_distance = dist
                        best_bbox = bbox
                if best_bbox is not None and min_distance < 100:
                    # Update the stored speaker bounding box  
                    self.speaker_bbox = best_bbox
                    self.lost_counter = 0
                else:
                    self.lost_counter += 1

            if self.lost_counter >= self.lost_threshold:
                print("Speaker lost for too many frames. Resetting locked on speaker.")
                self.speaker_bbox = None
                self.lost_counter = 0 


            return ([self.speaker_bbox] if self.speaker_bbox is not None else []), frame
