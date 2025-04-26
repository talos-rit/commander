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

        self.video_label = video_label #Label on the manual interface that shows the video feed with bounding boxes

        self.device = "cuda:0" if torch.cuda.is_available() else "cpu"
        self.object_detector = YOLO("yolo11n.pt")


        self.keep_away_mode = False
        self.countdown_start = None
        self.game_time_start = None
        self.final_time_outside_box = None
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

        detection_result = object_detector(frameRGB, classes=[0], verbose=False, imgsz=(576, 320), device=self.device)
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
            
        return bboxes
     

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

        if self.game_over:
            self.countdown_start = time.time()
            self.game_over = False
            self.keep_away_mode = True

        return bboxes, frame
    

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
                if self.game_time_start is None: # player did not even leave the box
                    self.final_time_outside_box = 0
                elif self.final_time_outside_box is None: # game is over, but final tiem has not been calculated
                    self.final_time_outside_box = time.time() - self.game_time_start
                
                text, scale, thickness = "GAME OVER", 3, 6
            else:
                if self.game_time_start is None:
                    self.game_time_start = time.time()
                text = None

            if text:
                (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, thickness)
                pos = ((w - tw)//2, (h + th)//2)
                cv2.putText(frame, text, pos, cv2.FONT_HERSHEY_SIMPLEX, scale, (0,0,255), thickness, cv2.LINE_AA)
                if self.game_over:
                    final_time_str = "SCORE:" + str(self.final_time_outside_box)
                    final_time_pos = (pos[0], pos[1] + th)
                    cv2.putText(frame, final_time_str, final_time_pos, cv2.FONT_HERSHEY_SIMPLEX, scale, (0,0,255), thickness, cv2.LINE_AA)


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