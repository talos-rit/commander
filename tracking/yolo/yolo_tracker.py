from tracking.tracker import Tracker
from ultralytics import YOLO
import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
import math
import yaml


class YOLOTracker(Tracker):

    # The tracker class is responsible for capturing frames from the source and detecting people in the frames
    def __init__(self, source : str, config_path):
        self.source = source

        self.object_detector = YOLO("yolo11m.pt")

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
        self.lost_threshold = 100

        self.speaker_color = None
        self.color_threshold = 15

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
        #print(detection_result)
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
        frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
        bboxes = self.detectPerson(self.object_detector, frame)
        
        self.draw_visuals(bboxes, frame)

        if self.speaker_bbox is None:
            # If no speaker is locked in yet, look for the X pose.
            # We assume only one person is in frame when the X pose is made.
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

                            smaller_box = self.getCroppedBox(box, frame)
                            color = self.get_dominant_color(smaller_box)
                            self.speaker_color = color
                            print("Speaker detected with X pose:", self.speaker_bbox)
                            return [self.speaker_bbox], frame

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
                best_bbox = None
                min_distance = float('inf')
                best_candidate_color = None

                for bbox in bboxes:
                    # Compute spatial distance.
                    dist = self.bbox_distance(bbox, self.speaker_bbox)
                    x1, y1, x2, y2 = bbox
                    smaller_box = self.getCroppedBox(bbox, frame)
                    color = self.get_dominant_color(smaller_box)
                    # Compute the Euclidean distance between the candidate color and the stored speaker color.
                    color_diff = abs(self.speaker_color - color)

                    #if dist < min_distance and color_diff < self.color_threshold:
                    if color_diff < self.color_threshold:
                        min_distance = dist
                        best_bbox = bbox
                        best_candidate_color = color

                #if best_bbox is not None and min_distance < 150:
                if best_bbox is not None:
                    # Found a candidate that is spatially close and with similar color.
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


    def getCroppedBox(self, bbox, frame):
        x1, y1, x2, y2 = bbox

        # Default crop is just middle of box
        height = y2 - y1
        width = x2 - x1
        chest_start = y1 + int(height * 0.3)
        chest_end = y1 + int(height * 0.5)
        exclude_extra = x1 + int(width * 0.4)
        exclude_extra2 = x1 + int(width * 0.6)
        chest_crop = frame[chest_start:chest_end, exclude_extra:exclude_extra2]

        return chest_crop

    #Draws acceptable box, bounding box, and center dot onto the video
    def draw_visuals(self, bounding_box, frame):

        for box in bounding_box:
            x1, y1, x2, y2 = box
            # Draw the rectangle on the frame (color = green, thickness = 2)
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

            x1, y1, x2, y2 = box

            # Default crop is just lower portion of the bbox
            height = y2 - y1
            width = x2 - x1
            chest_start = y1 + int(height * 0.3)
            chest_end = y1 + int(height * 0.5)
            exclude_extra = x1 + int(width * 0.3)
            exclude_extra2 = x1 + int(width * 0.7)
            chest_crop = frame[chest_start:chest_end, x1:x2]
            cv2.rectangle(frame, (exclude_extra, chest_start), (exclude_extra2, chest_end), (0, 150, 150), 2)

            dominant_color = self.get_dominant_color(chest_crop)

            # We'll use max saturation and value to show vivid color
            hsv_color = np.uint8([[[dominant_color, 255, 255]]])  # HSV image with 1 pixel
            bgr_color = cv2.cvtColor(hsv_color, cv2.COLOR_HSV2BGR)[0][0]  # Extract as (B, G, R)
            bgr_color = tuple(int(c) for c in bgr_color)

            patch_width = 30
            patch_height = 30
            patch_top_left = (x1, y1 - patch_height - 5)
            patch_bottom_right = (x1 + patch_width, y1 - 5)

            if patch_top_left[1] > 0:
                cv2.rectangle(frame, patch_top_left, patch_bottom_right, bgr_color, -1)

            label = f"Hue: {dominant_color}"
            cv2.putText(frame, label, (x1, y1 - patch_height - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255,255,255), 1, cv2.LINE_AA)

            color = (0, 255, 0)  # Green color for the center point
            radius = 10          # Radius of the circle
            thickness = -1       # -1 fills the circle

            bbox_center_x = (x1 + x2) // 2
            bbox_center_y = (y1 + y2) // 2

            cv2.circle(frame, (bbox_center_x, bbox_center_y), radius, color, thickness)


            # If speaker_bbox exists, draw line + distance
            if self.speaker_bbox is not None:
                sx1, sy1, sx2, sy2 = self.speaker_bbox
                speaker_center_x = (sx1 + sx2) // 2
                speaker_center_y = (sy1 + sy2) // 2

                cv2.circle(frame, (speaker_center_x, speaker_center_y), radius, (0, 0, 255), thickness)

                # Draw line
                cv2.line(frame, (bbox_center_x, bbox_center_y), (speaker_center_x, speaker_center_y), (255, 0, 0), 2)

                # Compute distance
                dist = math.sqrt((bbox_center_x - speaker_center_x) ** 2 + (bbox_center_y - speaker_center_y) ** 2)
                dist_text = f"{int(dist)} px"

                # Find midpoint of line to place label
                mid_x = (bbox_center_x + speaker_center_x) // 2
                mid_y = (bbox_center_y + speaker_center_y) // 2

                cv2.putText(frame, dist_text, (mid_x, mid_y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        cv2.imshow('Object Detection', frame)


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