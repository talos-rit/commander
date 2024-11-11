from tracking.tracker import Tracker
from publisher import Publisher
import time
import yaml
import cv2

class BasicDirector:
    # The director class is responsible for processing the frames captured by the tracker
    def __init__(self, tracker : Tracker, config_path):
        self.tracker = tracker
        self.config = self.load_config(config_path)
        self.frame_width = self.config['frame_width']
        self.frame_height = self.config['frame_height']
        self.acceptable_box_percent = self.config['acceptable_box_percent']
        self.horizontal_dpp = self.config['horizontal_field_of_view'] / self.frame_width
        self.vertical_dpp = self.config['vertical_field_of_view'] / self.frame_height
        self.confirmation_delay = self.config['confirmation_delay']
        self.command_delay = self.config['command_delay']
        self.last_command_time = 0  # Track the time of the last command
        self.movement_detection_start_time = None  # Time when the person first moved outside the box


    def load_config(self, config_path):
        with open(config_path, 'r') as file:
            return yaml.safe_load(file)
        
    def calculate_center_bounding_box(self, x, y, w, h):
        """
        Simple method to calculate the center of a bounding box
        """
        return (x + w) // 2, (y + h) // 2
    
    def calculate_acceptable_box(self):
        #Use the frame height and width to calculate an acceptable box
        # Calculate the frame's center
        frame_center_x = self.frame_width // 2
        frame_center_y = self.frame_height // 2

        # Define the acceptable box (50% of width and height around the center)
        acceptable_width = int(self.frame_width * self.acceptable_box_percent)
        acceptable_height = int(self.frame_height * self.acceptable_box_percent)

        acceptable_box_left = frame_center_x - (acceptable_width // 2)
        acceptable_box_top = frame_center_y - (acceptable_height // 2)
        acceptable_box_right = frame_center_x + (acceptable_width // 2)
        acceptable_box_bottom = frame_center_y + (acceptable_height // 2)
        return acceptable_box_left, acceptable_box_top, acceptable_box_right, acceptable_box_bottom


    # This method is called to process each frame
    def process_frame(self, frame : list):
    # Do something with the frame
        #print(frame)
        #print("Start of test")


        if len(frame) > 0:
            acceptable_box_left, acceptable_box_top, acceptable_box_right, acceptable_box_bottom = self.calculate_acceptable_box();

            #Calculate where the middle point of the bounding box lies in relation to the box
            # Unpack bounding box
            #Right now I am going to assume we only want the first face
            first_face = frame[0] # TODO change this later
            x, y, w, h = first_face

            # Calculate the center of the bounding box
            bbox_center_x, bbox_center_y = self.calculate_center_bounding_box(x, y, w, h)

            #Are we inside the acceptable box
            if (bbox_center_x < acceptable_box_left or bbox_center_x > acceptable_box_right or
                bbox_center_y < acceptable_box_top or bbox_center_y > acceptable_box_bottom):

                current_time = time.time()
                if self.movement_detection_start_time is None:
                    self.movement_detection_start_time = current_time

                # Check if they've been outside for at least the confirmation delay
                if current_time - self.movement_detection_start_time >= self.confirmation_delay:
                    change_in_x = 0
                    change_in_y = 0
                    #Move accordinly
                    #This is where it gets tricky, deciding how far to move the camera
                    if bbox_center_x < acceptable_box_left:
                        #print("Move camera left: " + "Bbox center x= " + str(bbox_center_x) + " acceptable left: " + str(acceptable_box_left))
                        change_in_x = bbox_center_x - acceptable_box_left
                    elif bbox_center_x > acceptable_box_right:
                        #print("Move camera right: " + "Bbox center x= " + str(bbox_center_x) + " acceptable right: " + str(acceptable_box_right))
                        change_in_x = bbox_center_x - acceptable_box_right
                    if bbox_center_y < acceptable_box_top:
                        #print("Move camera up: " + "Bbox center y= " + str(bbox_center_y) + " acceptable top: " + str(acceptable_box_top))
                        change_in_y = bbox_center_y - acceptable_box_top
                    elif bbox_center_y > acceptable_box_bottom:
                        #print("Move camera down: " + "Bbox center y= " + str(bbox_center_y) + " acceptable bottom: " + str(acceptable_box_bottom))
                        change_in_y = bbox_center_y - acceptable_box_bottom
                
                    if change_in_x != 0:
                        current_time = time.time()
                        if current_time - self.last_command_time >= self.command_delay or self.last_command_time == 0:
                            rotation = -(change_in_x * self.horizontal_dpp)
                            print(rotation)
                            rotation = int(round(rotation))
                            Publisher.polar_pan_discrete(rotation, 0, 0, 3000)
                            self.last_command_time = current_time
                            self.movement_detection_start_time = None

                    if change_in_y != 0:
                        current_time = time.time()
                        if current_time - self.last_command_time >= self.command_delay or self.last_command_time == 0:
                            rotation = change_in_y * self.vertical_dpp
                            print(rotation)
                            rotation = int(round(rotation))
                            #Publisher.rotate_altitude(rotation)
                            #Publisher.polar_pan_discrete(0, rotation, 0, 3000)
                            self.last_command_time = current_time
                            self.movement_detection_start_time = None
            else:
                self.movement_detection_start_time = None
