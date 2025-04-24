from tracking.tracker import Tracker
from ultralytics import YOLO
import cv2
import mediapipe as mp
import numpy as np
import time
import yaml
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
import math
import yaml
import torch
from PIL import Image, ImageTk


class KeepAwayTracker2(Tracker):

    # The tracker class is responsible for capturing frames from the source and detecting people in the frames
    def __init__(self, source : str, config_path, video_label):
        self.source = source

        self.config = self.load_config(config_path)
        # Open the video source
        if self.source:
            self.cap = cv2.VideoCapture(self.source)  
        else:
            camera_index = self.config['camera_index']
            self.cap = cv2.VideoCapture(camera_index)
        self.acceptable_box_percent = self.config['acceptable_box_percent']

        self.speaker_bbox = None

        self.video_label = video_label #Label on the manual interface that shows the video feed with bounding boxes

        self.device = "cuda:0" if torch.cuda.is_available() else "cpu"
        self.object_detector = YOLO("yolo11n.pt")

        self.pose_detector = YOLO("yolo11n-pose.pt")


        self.lost_counter = 0
        self.lost_threshold = 300

        self.speaker_color = None
        self.color_threshold = 15

        self.keep_away_mode = False
        self.countdown_start = None
        self.game_over = True

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

        frameSmall = cv2.resize(frameOpenCV, (inWidth, inHeight))
        frameRGB = cv2.cvtColor(frameSmall, cv2.COLOR_BGR2RGB)

        detection_result = object_detector(frameRGB, classes=0, verbose=False, imgsz=(576, 320), device=self.device)
        #print(detection_result)
        bboxes = []
        if detection_result:
            #print(detection_result[0].boxes.xyxyn)
            for xyxy in detection_result[0].boxes.xyxyn:
                x1 = int(xyxy[0] * frameWidth)
                y1 = int(xyxy[1] * frameHeight)
                x2 = int(xyxy[2] * frameWidth)
                y2 = int(xyxy[3] * frameHeight)
                bboxes.append((x1, y1, x2, y2))
            # for i, detection in enumerate(detection_result):
            #     xyxy = detection.boxes.xyxyn
            #     x1 = int(xyxy[i][0] * frameWidth)
            #     y1 = int(xyxy[i][1] * frameHeight)
            #     x2 = int(xyxy[i][2] * frameWidth)
            #     y2 = int(xyxy[i][3] * frameHeight)
            #     bboxes.append((x1, y1, x2, y2))
            # print(bboxes)
            

        return bboxes
    
    def is_x_pose_yolo(self, person_keypoints, threshold=0.1):
        """
        Given the keypoints for one person from a YOLOv8 pose detection,
        check if they are in the "X-Pose."

        'person_keypoints' is expected to be either:
        - shape (17, 2) -> (x, y)
        - shape (17, 3) -> (x, y, confidence)
        Indices: left_shoulder=5, right_shoulder=6, left_wrist=9, right_wrist=10 in COCO format.

        threshold: maximum vertical difference (normalized) allowed between wrists and shoulders.
        """

        # Ensure we have enough keypoints
        #print(person_keypoints[0])

        if person_keypoints.shape[1] < 11:
            return False


        kp_xy = person_keypoints.xyn[0]

        # Now kp_xy[i, 0] is x, kp_xy[i, 1] is y for keypoint i
        # For example, let's get the left shoulder (index 5) and right shoulder (index 6).

        x_ls  = float(kp_xy[5, 0])
        y_ls  = float(kp_xy[5, 1])
        x_rs = float(kp_xy[6, 0])
        y_rs = float(kp_xy[6, 1])
        x_lw  = float(kp_xy[10, 0])
        y_lw  = float(kp_xy[10, 1])
        x_rw = float(kp_xy[11, 0])
        y_rw = float(kp_xy[11, 1])
        #print("XLS" + str(x_ls))

        # 1) Check horizontal arrangement: left wrist < left shoulder AND right wrist > right shoulder
        if x_lw < x_ls and x_rw > x_rs:
            # 2) Check vertical difference
            vertical_diff_left  = abs(y_lw - y_ls)
            #print(vertical_diff_left)

            if (vertical_diff_left < threshold):
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
    def capture_frame(self, is_interface_running):

        hasFrame, frame = self.cap.read()
        if not hasFrame:
            return None, None
        #frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
        bboxes = self.detectPerson(self.object_detector, frame)
        
        self.draw_visuals(bboxes, frame, is_interface_running)

        self.change_video_frame(frame, is_interface_running)

        if self.speaker_bbox is None or self.game_over is True:
            # If no speaker is locked in yet, look for the X pose.
            # We assume only one person is in frame when the X pose is made.
            for box in bboxes:
                bbox = box
                x1, y1, x2, y2 = bbox
                cropped = frame[y1:y2, x1:x2]
                if cropped.size > 0:
                    cropped = cropped.astype("uint8")
                    # Run pose detection on the cropped image.
                    pose_result = self.pose_detector(cropped, verbose=False, device=self.device)
                    if len(pose_result) > 0:
                        # "results[0]" is the prediction for this single image/crop
                        result = pose_result[0]
                        if result.keypoints is not None:
                            if self.is_x_pose_yolo(result.keypoints):
                                self.speaker_bbox = box
                                smaller_box = self.getCroppedBox(box, frame)
                                color = self.get_dominant_color(smaller_box)
                                self.countdown_start = time.time()
                                self.game_over = False
                                self.keep_away_mode = True
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
            # Speaker is already locked. Find the current detection that is closest to the stored speaker bbox.
            best_bbox = None
            best_candidate_color = None

            for bbox in bboxes:
                x1, y1, x2, y2 = bbox
                smaller_box = self.getCroppedBox(bbox, frame)
                color = self.get_dominant_color(smaller_box)
                # Compute the Euclidean distance between the candidate color and the stored speaker color.
                color_diff = abs(self.speaker_color - color)

                if color_diff < self.color_threshold:
                    best_bbox = bbox
                    best_candidate_color = color

            if best_bbox is not None:
                # Found a candidate has similar color.
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
    

    def calculate_acceptable_box(self, frame_width, frame_height):
        """
        Get the values from the config to create the acceptable box of where the speaker can be without sending movements.
        Used in the drawing.
        Parameters:
        - bbox_width
        - frame_height 
        """
        #Use the frame height and width to calculate an acceptable box
        # Calculate the frame's center
        frame_center_x = frame_width // 2
        frame_center_y = frame_height // 2

        # Define the acceptable box (50% of width and height around the center)
        acceptable_width = int(frame_width * self.acceptable_box_percent)
        acceptable_height = int(frame_height * self.acceptable_box_percent)

        acceptable_box_left = frame_center_x - (acceptable_width // 2)
        acceptable_box_top = frame_center_y - (acceptable_height // 2)
        acceptable_box_right = frame_center_x + (acceptable_width // 2)
        acceptable_box_bottom = frame_center_y + (acceptable_height // 2)
        return acceptable_box_left, acceptable_box_top, acceptable_box_right, acceptable_box_bottom

    def draw_visuals(self, bounding_box, frame, is_interface_running):
        h, w = frame.shape[:2]

        # 1) Compute elapsed once
        if self.keep_away_mode:
            elapsed = time.time() - self.countdown_start
        else:
            elapsed = None

        # Draw acceptable box
        left, top, right, bottom = self.calculate_acceptable_box(w, h)
        cv2.rectangle(frame, (left, top), (right, bottom), (0, 0, 255), 2)

        # Before drawing boxes, if we're past the countdown and not yet game_over,
        #    check for a “catch” and set game_over.
        if self.keep_away_mode and elapsed is not None and elapsed >= 5 and not self.game_over:
            for x1, y1, x2, y2 in bounding_box:
                cx, cy = (x1 + x2)//2, (y1 + y2)//2
                if left < cx < right and top < cy < bottom:
                    self.game_over = True
                    break

        # Draw every bbox + center dot (green until caught, red if game_over and caught)
        for x1, y1, x2, y2 in bounding_box:
            cx, cy = (x1 + x2)//2, (y1 + y2)//2

            if self.keep_away_mode and self.game_over and left < cx < right and top < cy < bottom:
                box_color = (0, 0, 255)
            else:
                box_color = (0, 255, 0)

            cv2.rectangle(frame, (x1, y1), (x2, y2), box_color, 2)
            cv2.circle(frame, (cx, cy), 5, box_color, -1)

        # Overlay countdown or Game Over text on top
        if self.keep_away_mode:
            if elapsed < 5:
                text, scale, thickness = str(5 - int(elapsed)), 5, 8
            elif self.game_over:
                text, scale, thickness = "GAME OVER", 3, 6
            else:
                text = None

            if text:
                (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, thickness)
                pos = ((w - tw)//2, (h + th)//2)
                cv2.putText(frame, text, pos, cv2.FONT_HERSHEY_SIMPLEX, scale, (0,0,255), thickness, cv2.LINE_AA)

        # show
        if not is_interface_running:
            cv2.imshow('Object Detection', frame)


    def change_video_frame(self, frame, is_interface_running):
        if is_interface_running:
            # Once all drawings and processing are done, update the display.
            # Convert from BGR to RGB
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(frame_rgb)

            # Set desired dimensions (adjust these values as needed)
            desired_width = 640
            desired_height = 480
            pil_image = pil_image.resize((desired_width, desired_height), Image.Resampling.LANCZOS)

            imgtk = ImageTk.PhotoImage(image=pil_image)

            # Update the label
            self.video_label.after(0, lambda imgtk=imgtk: self.update_video_label(imgtk))

    def update_video_label(self, imgtk):
        self.video_label.config(image=imgtk)
        self.video_label.image = imgtk