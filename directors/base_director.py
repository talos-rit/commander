from abc import ABC, abstractmethod
import yaml
import cv2

class BaseDirector(ABC):

    def __init__(self, config_path):
        self.config = self.load_config(config_path)
        self.acceptable_box_percent = self.config['acceptable_box_percent']

    def load_config(self, config_path):
        with open(config_path, 'r') as file:
            return yaml.safe_load(file)

    # Calculates the center of the bounding box (our subject) 
    def calculate_center_bounding_box(self, x, y, w, h):
        """
        Simple method to calculate the center of a bounding box
        """
        return (x + w) // 2, (y + h) // 2
    
    #Function used to calculate the box we are trying to keep the subject in
    def calculate_acceptable_box(self, frame_width, frame_height):
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

    #Draws acceptable box, bounding box, and center dot onto the video
    def draw_visuals(self, x1, y1, x2, y2, acceptable_box_left, acceptable_box_top, acceptable_box_right, acceptable_box_bottom, frame):
        #print("draw")

        # Draw the rectangle on the frame (color = green, thickness = 2)
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

        color = (0, 0, 255)  # Green color for the rectangle
        thickness = 2  # Thickness of the rectangle lines
        cv2.rectangle(frame, (acceptable_box_left, acceptable_box_top), (acceptable_box_right, acceptable_box_bottom), color, thickness)

        color = (0, 255, 0)  # Green color for the center point
        radius = 10          # Radius of the circle
        thickness = -1       # -1 fills the circle

        bbox_center_x = (x1 + x2) // 2
        bbox_center_y = (y1 + y2) // 2

        cv2.circle(frame, (bbox_center_x, bbox_center_y), radius, color, thickness)

        # Display the frame with bounding boxes in a window
        cv2.imshow('Object Detection', frame)

    # Processes the bounding box and sends commands 
    @abstractmethod
    def process_frame(self):
        pass