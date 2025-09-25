import threading
import tkinter
from abc import ABC, abstractmethod

import cv2
from PIL import Image, ImageTk

from config import CAMERA_CONFIG


# Abstract class for tracking
class Tracker(ABC):
    speaker_bbox: list | None = None
    fps = CAMERA_CONFIG.get("fps", 60)
    camera_index = CAMERA_CONFIG["camera_index"]
    acceptable_box_percent = CAMERA_CONFIG["acceptable_box_percent"]
    desired_width = CAMERA_CONFIG.get("frame_width", None)
    desired_height = CAMERA_CONFIG.get("frame_height", None)

    is_video_running = False
    frame_update = False
    latest_frame = None  # Shared Resource: Store the latest frame captured
    lock = threading.Lock()

    def __init__(
        self,
        video_label: tkinter.Label | None,
        source: str | None = None,
        video_buffer_size=1,
    ):
        self.cap = cv2.VideoCapture(source or self.camera_index)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, video_buffer_size)  # Reduce buffer size

        self.video_label = video_label  # Label on the manual interface that shows the video feed with bounding boxes
        self.frame_delay = 1000 / self.fps

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
            if self.speaker_bbox is None:
                continue

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
        if not is_interface_running:
            return

        # Once all drawings and processing are done, update the display.
        # Convert from BGR to RGB
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(frame_rgb)

        dim = (self.desired_width, self.desired_height)
        if self.desired_height is None:
            # Set desired dimensions (adjust these values as needed)
            new_width = self.desired_width or 500
            aspect_ratio = float(frame.shape[1]) / float(frame.shape[0])
            new_height = int(new_width / aspect_ratio)

            # Create the new dimensions tuple (width, height)
            dim = (new_width, new_height)
        pil_image = pil_image.resize(dim, Image.Resampling.LANCZOS)
        image = ImageTk.PhotoImage(image=pil_image)
        # Update the label
        print("Changing video frame")
        self.frame_update = True
        self.latest_frame = image

    def start_video(self):
        if self.video_label is None or Tracker.is_video_running:
            return
        print("Starting video")
        Tracker.is_video_running = True
        thread = threading.Thread(target=self.frame_loop, daemon=True)
        thread.start()

    def frame_loop(self):
        while Tracker.is_video_running:
            print("frmae loop")
            # time.sleep(self.frame_delay)
            if self.video_label is not None:
                self.video_label.after(int(self.frame_delay), self.update)

    def stop_video(self):
        Tracker.is_video_running = False

    def update(self):
        print("Updating frame")
        if self.video_label is None or self.latest_frame is None:
            return
        self.frame_update = False
        self.video_label.config(image=self.latest_frame)
        # Keep a reference to prevent gc
        # see https://stackoverflow.com/questions/48364168/flickering-video-in-opencv-tkinter-integration
        self.video_label.dumb_image_ref = self.latest_frame  # pyright: ignore[reportAttributeAccessIssue]
