import time

from loguru import logger

import src.config as config
from src.connection.publisher import Direction, Publisher
from src.directors.base_director import BaseDirector
from src.tracking.vertical import named_joint_counts, select_vertical_motion
from src.utils import calculate_acceptable_box, calculate_center_bbox

_COUNT_FRESH_S = 1.25


class ContinuousDirector(BaseDirector):
    last_command_stop = False  # bool to ensure only one polar_pan_continuous_stop command is sent at a time
    last_command_time = 0  # Track the time of the last command
    # Time when the person first moved outside the box
    movement_detection_start_time = None

    # This method is called to process each frame
    def process_frame(
        self, hostname: str, bounding_box: list, frame_shape, publisher: Publisher
    ):
        """
        Based on received bounding box, this method tells the arm where to move the keep the subject in the acceptable box..
        It does this by continuously sending polar pan start and a direction until the subject is in the acceptable box.
        Then it sends a polar pan stop.
        """
        # Load config values
        confirmation_delay = config.ROBOT_CONFIGS[hostname].confirmation_delay
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

            # Adding a 1/10 of the frame buffer to the average so there is a 2/10 frame safety area
            frame_buffer = frame_height // 10
            center_top = center - frame_buffer
            center_bottom = center + frame_buffer

            if average < center_top:
                logger.debug(f"Move camera up: Average:{average} Center:{center}")
                change_in_y = average - center_top
            elif average > center_bottom:
                logger.debug(f"Move camera down: Average:{average} Center:{center}")
                change_in_y = average - center_bottom

            # One axis at a time. Horizontal pan wins a tie; a larger vertical error waits for it.
            horizontal = change_in_x != 0 and (change_in_y == 0 or abs(change_in_x) >= abs(change_in_y))
            if horizontal and change_in_x > 0:
                self._command(hostname, publisher, ("polar", Direction.RIGHT))
                logger.debug("start right")
            elif horizontal:
                self._command(hostname, publisher, ("polar", Direction.LEFT))
                logger.debug("start left")
            elif change_in_y != 0:
                self._command_vertical(hostname, publisher, image_up=change_in_y < 0)
            else:
                self._release(hostname, publisher)
            return
        self._release(hostname, publisher)
        self.movement_detection_start_time = None

    def _command_vertical(self, hostname: str, publisher: Publisher, image_up: bool) -> None:
        robot = config.ROBOT_CONFIGS[hostname]
        counts, fresh = self._read_counts(publisher)
        named = named_joint_counts(counts)
        motion = select_vertical_motion(
            elbow=bool(getattr(robot, "track_elbow", False)),
            shoulder=bool(getattr(robot, "track_shoulder", False)),
            polar_vertical=bool(getattr(robot, "track_polar_vertical", True)),
            image_up=image_up,
            elbow_count=named.get("elbow"),
            shoulder_count=named.get("shoulder"),
            pitch_count=named.get("pitch"),
            counts_fresh=fresh,
            elbow_limits=_limit_pair(robot, "elbow_count_min", "elbow_count_max"),
            shoulder_limits=_limit_pair(robot, "shoulder_count_min", "shoulder_count_max"),
            pitch_limits=_limit_pair(robot, "pitch_count_min", "pitch_count_max"),
        )
        if motion is None:
            logger.info("Vertical tracking held; no enabled axis can move.")
            self._release(hostname, publisher)
            return
        if motion[0] == "polar":
            self._command(hostname, publisher, ("polar", Direction.UP if motion[1] > 0 else Direction.DOWN))
            return
        self._command(hostname, publisher, motion)

    def _command(self, hostname: str, publisher: Publisher, motion: tuple) -> None:
        """Start or refresh one tracking motion. A joint jog and a polar pan are different operations."""
        current = self._motions().get(hostname)
        if current is not None and current[0] != motion[0]:
            self._halt(publisher, current)
        elif current is not None and current[0] == "joint" and current != motion:
            publisher.erv_joint_jog_stop()
        if motion[0] == "joint":
            publisher.erv_joint_jog_start(motion[1], motion[2])
        else:
            publisher.polar_pan_continuous_direction_start(motion[1])
        self._motions()[hostname] = motion
        self.last_command_stop = False

    def _release(self, hostname: str, publisher: Publisher) -> None:
        current = self._motions().pop(hostname, None)
        if current is None:
            if not self.last_command_stop:
                publisher.polar_pan_continuous_stop()
                self.last_command_stop = True
            return
        self._halt(publisher, current)
        self.last_command_stop = True

    def _motions(self) -> dict:
        motions = getattr(self, "_tracking_motion", None)
        if motions is None:
            motions = {}
            self._tracking_motion = motions
        return motions

    def _halt(self, publisher: Publisher, motion: tuple) -> None:
        if motion[0] == "joint":
            stop = getattr(publisher, "erv_joint_jog_stop", None)
            if stop is not None:
                stop()
            return
        publisher.polar_pan_continuous_stop()

    def _read_counts(self, publisher: Publisher) -> tuple[tuple | None, bool]:
        if getattr(publisher, "tracking_joint_counts", None) is not None or hasattr(
            publisher, "tracking_joint_counts_at"
        ):
            counts = getattr(publisher, "tracking_joint_counts", None)
            received = getattr(publisher, "tracking_joint_counts_at", None)
        elif hasattr(publisher, "_telemetry_lock"):
            counts = publisher.get_erv_joint_counts()
            received = publisher.get_erv_telemetry_received_monotonic()
        else:
            return None, False
        fresh = received is not None and time.monotonic() - received <= _COUNT_FRESH_S
        return counts, fresh


def _limit_pair(robot, low_name: str, high_name: str) -> tuple[int, int] | None:
    low = getattr(robot, low_name, None)
    high = getattr(robot, high_name, None)
    if low is None or high is None:
        return None
    return (low, high)
