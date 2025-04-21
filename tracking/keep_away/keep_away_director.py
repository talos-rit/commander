from tracking.tracker import Tracker
from directors.base_director import BaseDirector
from publisher import Publisher
import time
import yaml
import cv2

class KeepAwayDirector(BaseDirector):
    # The director class is responsible for processing the frames captured by the tracker
    def __init__(self, tracker : Tracker, config_path):
        super().__init__(config_path)
        self.last_command_stop = False # bool to ensure only one polar_pan_continuous_stop command is sent at a time
        self.tracker = tracker
        self.confirmation_delay = self.config['confirmation_delay']
        self.command_delay = self.config['command_delay']
        self.last_command_time = 0  # Track the time of the last command
        self.movement_detection_start_time = None  # Time when the person first moved outside the box


    # This method is called to process each frame
    def process_frame(self, bounding_box : list, frame, is_director_running):
        """
        Based on received bounding box, this method tells the arm where to move the keep the subject in the acceptable box..
        It does this by continuously sending polar pan start and a direction until the subject is in the acceptable box.
        Then it sends a polar pan stop.    
        """
        frameOpenCV = frame.copy()
        frame_height = frameOpenCV.shape[0]
        frame_width = frameOpenCV.shape[1]

        if len(bounding_box) > 0:
            acceptable_box_left, acceptable_box_top, acceptable_box_right, acceptable_box_bottom = self.calculate_acceptable_box(frame_width, frame_height)   

            #C alculate where the middle point of the bounding box lies in relation to the box
            # Unpack bounding box
            # If there is a single speaker it should return one bounding box anyway
            first_face = bounding_box[0] 
            x, y, w, h = first_face

            top = y
            bottom = y + h
            center = frame_height // 2
            average = (top + bottom) // 2

            # Calculate the center of the bounding box
            bbox_center_x, bbox_center_y = self.calculate_center_bounding_box(x, y, w, h)

            if is_director_running: 
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

                        #Adding a 1/10 of the frame buffer to the average so there is a 2/10 frame safety area
                        frame_buffer = frame_height // 10
                        center_top = center - frame_buffer
                        center_bottom = center + frame_buffer

                        if average < center_top:
                            #print("Move camera up: " + "Average: " + str(average) + " Center: " + str(center))
                            change_in_y = average - center_top
                        elif average > center_bottom:
                            #print("Move camera down: " + "Average: " + str(average) + " Center: " + str(center))
                            change_in_y = average - center_bottom

                        if change_in_x > 0:
                            Publisher.polar_pan_continuous_start(-1, 0)
                            #print("start")
                            self.last_command_stop = False
                        elif change_in_x < 0:
                            Publisher.polar_pan_continuous_start(1, 0)
                            #print("start")
                            self.last_command_stop = False
                        elif change_in_y < 0:
                            Publisher.polar_pan_continuous_start(0, 1)
                            #print("start")
                            self.last_command_stop = False
                        elif change_in_y > 0:
                            Publisher.polar_pan_continuous_start(0, -1)
                            #print("start")
                            self.last_command_stop = False
                        else:
                            if(not self.last_command_stop):
                                Publisher.polar_pan_continuous_stop()
                                self.last_command_stop = True
                    
                else:
                    if(not self.last_command_stop):
                        Publisher.polar_pan_continuous_stop()
                        print("Stop")
                        self.last_command_stop = True

                    self.movement_detection_start_time = None

    
