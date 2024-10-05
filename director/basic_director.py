from tracking.tracker import Tracker

class BasicDirector:
    # The director class is responsible for processing the frames captured by the tracker
    def __init__(self, tracker : Tracker):
        self.tracker = tracker

    # This method is called to process each frame
    def process_frame(self, frame : list, frameHeight: int, frameWidth: int):
    # Do something with the frame
        print(frame)
        #Code underneath is unnecessary until we figure out which algorithm to  use
        """
        if len(frame) > 0:

            #Use the frame height and width to calculate an acceptable box
            # Calculate the frame's center
            frame_center_x = frameWidth // 2
            frame_center_y = frameHeight // 2

            # Define the acceptable box (50% of width and height around the center)
            acceptable_width = int(frameWidth * 0.5)
            acceptable_height = int(frameHeight * 0.5)

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

                #Move accordinly
                #This is where it gets tricky, deciding how far to move the camera
                if bbox_center_x < acceptable_box_left:
                    print("Move camera left: " + "Bbox center x= " + str(bbox_center_x) + " acceptable left: " + str(acceptable_box_left))
                elif bbox_center_x > acceptable_box_right:
                    print("Move camera right: " + "Bbox center x= " + str(bbox_center_x) + " acceptable right: " + str(acceptable_box_right))
                if bbox_center_y < acceptable_box_top:
                    print("Move camera up: " + "Bbox center y= " + str(bbox_center_y) + " acceptable top: " + str(acceptable_box_top))
                elif bbox_center_y > acceptable_box_bottom:
                    print("Move camera down: " + "Bbox center y= " + str(bbox_center_y) + " acceptable bottom: " + str(acceptable_box_bottom))
        """