from tracking.tracker import Tracker
from directors.base_director import BaseDirector
from publisher import Publisher
import time
import yaml
import cv2

class DiscreteDirector(BaseDirector):
    # The director class is responsible for processing the frames captured by the tracker
    def __init__(self, tracker : Tracker, config_path):
        super().__init__(config_path)
        self.tracker = tracker
        self.horizontal_field_of_view = self.config['horizontal_field_of_view']
        self.vertical_field_of_view = self.config['vertical_field_of_view']
        self.confirmation_delay = self.config['confirmation_delay']
        self.command_delay = self.config['command_delay']
        self.last_command_time = 0  # Track the time of the last command
        self.movement_detection_start_time = None  # Time when the person first moved outside the box


    # This method is called to process each frame
    def process_frame(self, bounding_box : list, frame):
    # Do something with the frame

        #Getting frame width and frame height
        frameOpenCV = frame.copy()
        frame_height = frameOpenCV.shape[0]
        frame_width = frameOpenCV.shape[1]


        if len(bounding_box) > 0:
            acceptable_box_left, acceptable_box_top, acceptable_box_right, acceptable_box_bottom = self.calculate_acceptable_box(frame_width, frame_height);

            #Calculate where the middle point of the bounding box lies in relation to the box
            # Unpack bounding box
            #Right now I am going to assume we only want the first face
            first_face = bounding_box[0] # TODO change this later
            x, y, w, h = first_face

            #Draw on visuals
            self.draw_visuals(x, y, w, h, acceptable_box_left, acceptable_box_top, acceptable_box_right, acceptable_box_bottom, frame)

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
                            horizontal_dpp = self.horizontal_field_of_view / frame_width
                            rotation = -(change_in_x * horizontal_dpp)
                            print(rotation)
                            rotation = int(round(rotation))
                            Publisher.polar_pan_discrete(rotation, 0, 0, 3000)
                            self.last_command_time = current_time
                            self.movement_detection_start_time = None

                    if change_in_y != 0:
                        current_time = time.time()
                        if current_time - self.last_command_time >= self.command_delay or self.last_command_time == 0:
                            vertical_dpp = self.vertical_field_of_view / frame_height
                            rotation = change_in_y * vertical_dpp
                            print(rotation)
                            rotation = int(round(rotation))
                            #Publisher.rotate_altitude(rotation)
                            #Publisher.polar_pan_discrete(0, rotation, 0, 3000)
                            self.last_command_time = current_time
                            self.movement_detection_start_time = None
            else:
                self.movement_detection_start_time = None