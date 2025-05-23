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


    # Processes the bounding box and sends commands 
    @abstractmethod
    def process_frame(self):
        pass