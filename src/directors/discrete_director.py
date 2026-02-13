import time

from loguru import logger

from src.config import CONFIG
from src.connection.publisher import Publisher
from src.directors.base_director import BaseDirector
from src.utils import (
    calculate_acceptable_box,
    calculate_center_bbox,
)


class DiscreteDirector(BaseDirector):
    config = CONFIG
    last_command_time = 0  # Track the time of the last command

    # Time when the person first moved outside the box
    movement_detection_start_time = None

    # This method is called to process each frame
    def process_frame(
        self, hostname: str, bounding_box: list, frame_shape, publisher: Publisher
    ):
        # Load config values
        horizontal_field_of_view = CONFIG[hostname].horizontal_field_of_view
        vertical_field_of_view = CONFIG[hostname].vertical_field_of_view
        confirmation_delay = CONFIG[hostname].confirmation_delay
        command_delay = CONFIG[hostname].command_delay
        # Do something with the frame

        # Getting frame width and frame height
        frame_height = frame_shape[0]
        frame_width = frame_shape[1]

        if len(bounding_box) == 0:
            return
        (
            acceptable_box_left,
            acceptable_box_top,
            acceptable_box_right,
            acceptable_box_bottom,
        ) = calculate_acceptable_box(frame_width, frame_height)
        # Calculate where the middle point of the bounding box lies in relation to the box
        # Unpack bounding box
        # TODO: Right now I am going to assume we only want the first face

        # Calculate the center of the bounding box
        bbox_center_x, bbox_center_y = calculate_center_bbox(bounding_box[0])

        # Are we inside the acceptable box
        if (
            bbox_center_x < acceptable_box_left
            or bbox_center_x > acceptable_box_right
            or bbox_center_y < acceptable_box_top
            or bbox_center_y > acceptable_box_bottom
        ):
            current_time = time.time()
            if self.movement_detection_start_time is None:
                self.movement_detection_start_time = current_time

            # Check if they've been outside for at least the confirmation delay
            if current_time - self.movement_detection_start_time < confirmation_delay:
                return

            change_in_x = 0
            change_in_y = 0
            # Move accordinly
            # This is where it gets tricky, deciding how far to move the camera
            if bbox_center_x < acceptable_box_left:
                # print("Move camera left: " + "Bbox center x= " + str(bbox_center_x) + " acceptable left: " + str(acceptable_box_left))
                change_in_x = bbox_center_x - acceptable_box_left
            elif bbox_center_x > acceptable_box_right:
                # print("Move camera right: " + "Bbox center x= " + str(bbox_center_x) + " acceptable right: " + str(acceptable_box_right))
                change_in_x = bbox_center_x - acceptable_box_right
            if bbox_center_y < acceptable_box_top:
                # print("Move camera up: " + "Bbox center y= " + str(bbox_center_y) + " acceptable top: " + str(acceptable_box_top))
                change_in_y = bbox_center_y - acceptable_box_top
            elif bbox_center_y > acceptable_box_bottom:
                # print("Move camera down: " + "Bbox center y= " + str(bbox_center_y) + " acceptable bottom: " + str(acceptable_box_bottom))
                change_in_y = bbox_center_y - acceptable_box_bottom

            if change_in_x != 0 and (
                current_time - self.last_command_time >= command_delay
                or self.last_command_time == 0
            ):
                horizontal_dpp = horizontal_field_of_view / frame_width
                rotation = -(change_in_x * horizontal_dpp)
                logger.info(rotation)
                rotation = int(round(rotation))
                publisher.polar_pan_discrete(rotation, 0, 0, 3000)
                self.last_command_time = current_time
                self.movement_detection_start_time = None

            if change_in_y == 0:
                return
            if (
                current_time - self.last_command_time >= command_delay
                or self.last_command_time == 0
            ):
                vertical_dpp = vertical_field_of_view / frame_height
                rotation = change_in_y * vertical_dpp
                logger.info(rotation)
                rotation = int(round(rotation))
                # publisher.rotate_altitude(rotation)
                # publisher.polar_pan_discrete(0, rotation, 0, 3000)
                self.last_command_time = current_time
                self.movement_detection_start_time = None
        else:
            self.movement_detection_start_time = None
