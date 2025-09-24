from abc import ABC, abstractmethod

import cv2
import yaml
from PIL import Image, ImageTk


# Abstract class for tracking
class Tracker(ABC):
    speaker_bbox: list | None = None

    def __init__(self, source: str, config_path, video_label):
        self.source = source

        self.config = self.load_config(config_path)
        # Open the video source
        if self.source:
            self.cap = cv2.VideoCapture(self.source)
        else:
            camera_index = self.config["camera_index"]
            self.cap = cv2.VideoCapture(camera_index)
        self.acceptable_box_percent = self.config["acceptable_box_percent"]

        self.speaker_bbox = None

        self.video_label = video_label  # Label on the manual interface that shows the video feed with bounding boxes

    def load_config(self, config_path):
        with open(config_path, "r") as file:
            return yaml.safe_load(file)

    # Capture a frame from the source
    @abstractmethod
    def capture_frame(self):
        pass

    def calculate_acceptable_box(self, frame_width, frame_height):
        """
        Get the values from the config to create the acceptable box of where the speaker can be without sending movements.
        Used in the drawing.
        Parameters:
        - bbox_width
        - frame_height
        """
        # Use the frame height and width to calculate an acceptable box
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
        return (
            acceptable_box_left,
            acceptable_box_top,
            acceptable_box_right,
            acceptable_box_bottom,
        )

    # Draws acceptable box, bounding box, and center dot onto the video
    def draw_visuals(self, bounding_box, frame, is_interface_running):
        """
        Draws all the visuals we need on the frame. Rectangles around bounding boxes, circles in the middle, acceptable box for director, red dot for speaker.

        Parameters:
        - bounding_box - bounding boxes from capture frame
        - frame - frame to draw on
        """
        # Draw the acceptable box
        frame_height = frame.shape[0]
        frame_width = frame.shape[1]
        (
            acceptable_box_left,
            acceptable_box_top,
            acceptable_box_right,
            acceptable_box_bottom,
        ) = self.calculate_acceptable_box(frame_width, frame_height)
        color = (0, 0, 255)  # Green color for the rectangle
        thickness = 2  # Thickness of the rectangle lines
        cv2.rectangle(
            frame,
            (acceptable_box_left, acceptable_box_top),
            (acceptable_box_right, acceptable_box_bottom),
            color,
            thickness,
        )

        for box in bounding_box:
            # Draw each bbox
            x1, y1, x2, y2 = box
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

            color = (0, 255, 0)  # Green color for the center point
            radius = 10  # Radius of the circle
            thickness = -1  # -1 fills the circle

            bbox_center_x = (x1 + x2) // 2
            bbox_center_y = (y1 + y2) // 2

            # Draw center of bounding box dot, this the value the commander is using
            cv2.circle(frame, (bbox_center_x, bbox_center_y), radius, color, thickness)

            # If speaker_bbox exists, draw line + distance
            if self.speaker_bbox is not None:
                # Draw where the tracker is taking the color from - t-shirt area
                height = y2 - y1
                width = x2 - x1
                chest_start = y1 + int(height * 0.3)
                chest_end = y1 + int(height * 0.5)
                exclude_extra = x1 + int(width * 0.4)
                exclude_extra2 = x1 + int(width * 0.6)
                cv2.rectangle(
                    frame,
                    (exclude_extra, chest_start),
                    (exclude_extra2, chest_end),
                    (0, 150, 150),
                    2,
                )

                sx1, sy1, sx2, sy2 = self.speaker_bbox
                speaker_center_x = (sx1 + sx2) // 2
                speaker_center_y = (sy1 + sy2) // 2
                # Red circle for speaker bbox
                cv2.circle(
                    frame,
                    (speaker_center_x, speaker_center_y),
                    radius,
                    (0, 0, 255),
                    thickness,
                )

        if not is_interface_running:
            cv2.imshow("Object Detection", frame)

    def change_video_frame(self, frame, is_interface_running):
        if is_interface_running:
            # Once all drawings and processing are done, update the display.
            # Convert from BGR to RGB
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(frame_rgb)

            # Set desired dimensions (adjust these values as needed)
            desired_width = 640
            desired_height = 480
            pil_image = pil_image.resize(
                (desired_width, desired_height), Image.Resampling.LANCZOS
            )

            imgtk = ImageTk.PhotoImage(image=pil_image)

            # Update the label
            self.video_label.after(
                0, lambda imgtk=imgtk: self.update_video_label(imgtk)
            )

    def update_video_label(self, imgtk):
        self.video_label.config(image=imgtk)
        self.video_label.image = imgtk
