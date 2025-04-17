import math
import cv2
import yaml
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
from tracking.tracker import Tracker


class MediaPipePose(Tracker):

    # The tracker class is responsible for capturing frames from the source and detecting people in the frames
    def __init__(self, source : str, config_path, video_label):
        self.speaker_bbox = None  #Shared reference. Only here to avoid pylint errors.
        super().__init__(source, config_path, video_label)

        base_options = python.BaseOptions(model_asset_path="tracking/media_pipe/efficientdet_lite0.tflite")
        options = vision.ObjectDetectorOptions(base_options=base_options, score_threshold=0.5, category_allowlist=["person"])
        self.object_detector = vision.ObjectDetector.create_from_options(options)


        pose_base_options = python.BaseOptions(model_asset_path="tracking/media_pipe/pose_landmarker_lite.task")
        pose_options = vision.PoseLandmarkerOptions(
            base_options=pose_base_options,
            # Additional options (e.g., running on CPU) can be specified here.
        )
        self.pose_detector = vision.PoseLandmarker.create_from_options(pose_options)

        self.lost_counter = 0
        self.lost_threshold = 100

        self.speaker_color = None
        self.color_threshold = 15



    # Detect people in the frame
    def detectPerson(self, object_detector, frame, inHeight=500, inWidth=0):
        """
        Uses mediapipe to find all people in the frame and returns the bounding boxes of those people.
        """
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


    def capture_frame(self, is_interface_running):
        """
        Finds all the people in the frame, and then decides what to send to the director.
        Looks for x pose to determine primary speaker.
        Uses color matching to maintain that primary speaker.
        Sends primary speaker box to the director.    
        """
        hasFrame, frame = self.cap.read()
        if not hasFrame:
            return None, None

        #Use this rotate if the mp4 is showing up incorrectly
        #frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)

        bboxes = self.detectPerson(self.object_detector, frame)

        self.draw_visuals(bboxes, frame, is_interface_running)

        self.change_video_frame(frame, is_interface_running)

        if self.speaker_bbox is None:
            # If no speaker is locked in yet, look for the X pose.
            for box in bboxes:
                bbox = box
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

                            smaller_box = self.get_cropped_box(box, frame)
                            color = self.get_dominant_color(smaller_box)
                            self.speaker_color = color
                            print("Speaker detected with X pose:", self.speaker_bbox)
                            return [self.speaker_bbox], frame

            # While speaker not yet locked, return all detected bounding boxes.
            # This will just have the director track whichever it sees first. If there is only one person in frame this is fine
            return bboxes, frame
        

        # If frame is empty after detecting a speaker, increment the lost speaker counter
        if len(bboxes) == 0:
            # No detections
            self.lost_counter += 1
        else:
            # Speaker is already locked. Find the current detection that is closest to the stored speaker bbox. Based solely on color.
            best_bbox = None
            best_candidate_color = None

            for bbox in bboxes:
                x1, y1, x2, y2 = bbox
                smaller_box = self.get_cropped_box(bbox, frame)
                color = self.get_dominant_color(smaller_box)
                # Compute the Euclidean distance between the candidate color and the stored speaker color.
                color_diff = abs(self.speaker_color - color)

                if color_diff < self.color_threshold:
                    best_bbox = bbox
                    best_candidate_color = color

            if best_bbox is not None:
                # Found a candidate that has similar color.
                self.speaker_bbox = best_bbox
                self.speaker_color = best_candidate_color
                self.lost_counter = 0
            else:
                self.lost_counter += 1

        if self.lost_counter >= self.lost_threshold:
            print("Speaker lost for too many frames. Resetting single speaker.")
            self.speaker_bbox = None
            self.speaker_color = None
            self.lost_counter = 0


        return ([self.speaker_bbox] if self.speaker_bbox is not None else []), frame
        

    def compute_center(self, bbox):
        """Compute the center of a bounding box."""
        x1, y1, x2, y2 = bbox
        return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)

    def get_cropped_box(self, bbox, frame):
        """
        Get cropped box for color tracking. Takes a much smaller portion of the bbox to get most dominant color.
        
        Parameters:
        - bbox - Current bounding box we are looking at
        - frame 
        """
        x1, y1, x2, y2 = bbox

        # Default crop is just middle of box, where t-shirt is
        height = y2 - y1
        width = x2 - x1
        chest_start = y1 + int(height * 0.3)
        chest_end = y1 + int(height * 0.5)
        exclude_extra = x1 + int(width * 0.4)
        exclude_extra2 = x1 + int(width * 0.6)
        chest_crop = frame[chest_start:chest_end, exclude_extra:exclude_extra2]

        return chest_crop



    def get_dominant_color(self, image, quantize_level=16):
        """
        Finds the most dominant color in an image using color quantization.
        
        Parameters:
        - image: cropped region (H x W x 3)
        - quantize_level: smaller numbers = more grouping (e.g., 24, 32)
        
        Returns:
        - Dominant color as (B, G, R)
        """
        # Resize to reduce noise and speed up

        image = cv2.resize(image, (50, 50), interpolation=cv2.INTER_AREA)
        #image = cv2.GaussianBlur(image, (5, 5), 0)

        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        hue_channel = hsv[:, :, 0]  # Hue ranges from 0 to 179 in OpenCV

        # Quantize hue values
        quantized_hue = (hue_channel // quantize_level) * quantize_level

        # Flatten and find the most common hue bin
        unique_hues, counts = np.unique(quantized_hue.flatten(), return_counts=True)
        dominant_hue = unique_hues[np.argmax(counts)]

        return int(dominant_hue)
    
    
