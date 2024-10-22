from tracking.tracker import Tracker
from publisher import Publisher
import time

class BasicDirector:
    # The director class is responsible for processing the frames captured by the tracker
    def __init__(self, tracker : Tracker):
        self.tracker = tracker
        self.last_command_time = 0  # Track the time of the last command
        self.command_delay = 8  # 5 seconds delay between commands
        self.movement_detection_start_time = None  # Time when the person first moved outside the box
        self.confirmation_delay = 2  # Time the person must remain outside before sending a command (in seconds)

    # This method is called to process each frame
    def process_frame(self, frame : list):
    # Do something with the frame
        #print(frame)

        isTwinTest = True
        if isTwinTest:
            self.digital_twin_update(frame)


    def digital_twin_update(self, frame : list):
        #print("Start of test")

        #Hardcoding resolution values for now based on smartphone video
        acceptable_box_percent = 0.5
        frame_width = 320
        frame_height = 568
        vertical_field_of_view = 90
        horizontal_field_of_view = 60

        #Calculating degrees per pixel
        horizontal_dpp = horizontal_field_of_view / frame_width
        vertical_dpp = vertical_field_of_view / frame_height

        if len(frame) > 0:
            #Use the frame height and width to calculate an acceptable box
            # Calculate the frame's center
            frame_center_x = frame_width // 2
            frame_center_y = frame_height // 2

            # Define the acceptable box (50% of width and height around the center)
            acceptable_width = int(frame_width * acceptable_box_percent)
            acceptable_height = int(frame_height * acceptable_box_percent)

            acceptable_box_left = frame_center_x - (acceptable_width // 2)
            acceptable_box_top = frame_center_y - (acceptable_height // 2)
            acceptable_box_right = frame_center_x + (acceptable_width // 2)
            acceptable_box_bottom = frame_center_y + (acceptable_height // 2)

            #Calculate where the middle point of the bounding box lies in relation to the box
            # Unpack bounding box
            #Right now I am going to assume we only want the first face
            first_face = frame[0]
            x, y, w, h = first_face

            # Calculate the center of the bounding box
            bbox_center_x = x + (w // 2)
            bbox_center_y = y + (h // 2)

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
                            rotation = -(change_in_x * horizontal_dpp)
                            print(rotation)
                            Publisher.rotate_azimuth(rotation)
                            self.last_command_time = current_time
                            self.movement_detection_start_time = None

                    if change_in_y != 0:
                        current_time = time.time()
                        if current_time - self.last_command_time >= self.command_delay or self.last_command_time == 0:
                            rotation = change_in_y * vertical_dpp
                            print(rotation)
                            Publisher.rotate_altitude(rotation)
                            self.last_command_time = current_time
                            self.movement_detection_start_time = None
            else:
                self.movement_detection_start_time = None