import time

from config.config import DEFAULT_CONFIG
from directors.base_director import BaseDirector
from publisher import Publisher
from utils import (
    calculate_acceptable_box,
    calculate_center_bbox,
)


class KeepAwayDirector(BaseDirector):
    # Time when the person first moved outside the box
    movement_detection_start_time: float | None = None
    # Track the time of the last command
    last_command_time = 0
    # bool to ensure only one polar_pan_continuous_stop command is sent at a time
    last_command_stop = False

    confirmation_delay = DEFAULT_CONFIG["confirmation_delay"]
    command_delay = DEFAULT_CONFIG["command_delay"]

    # This method is called to process each frame
    def process_frame(self, bounding_box: list, frame, is_director_running):
        """
        Based on received bounding box, this method tells the arm where to move the keep the subject in the acceptable box..
        It does this by continuously sending polar pan start and a direction until the subject is in the acceptable box.
        Then it sends a polar pan stop.
        """
        frameOpenCV = frame.copy()
        frame_height = frameOpenCV.shape[0]
        frame_width = frameOpenCV.shape[1]

        if len(bounding_box) == 0:
            return
        (
            acceptable_box_left,
            acceptable_box_top,
            acceptable_box_right,
            acceptable_box_bottom,
        ) = calculate_acceptable_box(frame_width, frame_height)

        # C alculate where the middle point of the bounding box lies in relation to the box
        # Unpack bounding box
        # If there is a single speaker it should return one bounding box anyway
        first_face = bounding_box[0]
        x, y, w, h = first_face

        top = y
        bottom = y + h
        center = frame_height // 2
        average = (top + bottom) // 2

        # Calculate the center of the bounding box
        bbox_center_x, bbox_center_y = calculate_center_bbox(first_face)

        if not is_director_running:
            return

        # Stop polar pan if the subject is back in the box
        if (
            bbox_center_x > acceptable_box_left
            and bbox_center_x < acceptable_box_right
            and bbox_center_y > acceptable_box_top
            and bbox_center_y < acceptable_box_bottom
        ):
            if not self.last_command_stop:
                Publisher.polar_pan_continuous_stop()
                print("Stop")
                self.last_command_stop = True

            self.movement_detection_start_time = None
            return

        current_time = time.time()
        if self.movement_detection_start_time is None:
            self.movement_detection_start_time = current_time
            return

        # Check if they've been outside for at least the confirmation delay
        detected_duration = current_time - self.movement_detection_start_time
        if detected_duration < self.confirmation_delay:
            return
        change_in_x = change_in_y = 0
        # Move accordinly
        # This is where it gets tricky, deciding how far to move the camera
        if bbox_center_x < acceptable_box_left:
            change_in_x = bbox_center_x - acceptable_box_left
        elif bbox_center_x > acceptable_box_right:
            change_in_x = bbox_center_x - acceptable_box_right

        # Adding a 1/10 of the frame buffer to the average so there is a 2/10 frame safety area
        frame_buffer = frame_height // 10
        center_top = center - frame_buffer
        center_bottom = center + frame_buffer

        if average < center_top:
            change_in_y = average - center_top
        elif average > center_bottom:
            change_in_y = average - center_bottom

        if change_in_x > 0:
            Publisher.polar_pan_continuous_start(-1, 0)
            self.last_command_stop = False
        elif change_in_x < 0:
            Publisher.polar_pan_continuous_start(1, 0)
            self.last_command_stop = False
        elif change_in_y < 0:
            Publisher.polar_pan_continuous_start(0, 1)
            self.last_command_stop = False
        elif change_in_y > 0:
            Publisher.polar_pan_continuous_start(0, -1)
            self.last_command_stop = False
        elif not self.last_command_stop:
            Publisher.polar_pan_continuous_stop()
            self.last_command_stop = True
