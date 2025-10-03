import multiprocessing
from abc import ABC, abstractmethod
from queue import Empty

import cv2
from PIL import Image, ImageTk

from config import ROBOT_CONFIGS
from tkscheduler import IterativeTask, Scheduler
from utils import (
    add_termination_handler,
    calculate_acceptable_box,
    calculate_center_bbox,
)

# Temporary hardcoded index to until hostname can be passed in
CONFIG = ROBOT_CONFIGS["operator.talos"]

class ObjectModel(ABC):
    """
    This is a model class where it can handle turning image frame into bounding box
    The reason why this is separated is due to the fact that this will be running in a separate process.
    """

    speaker_bbox: tuple[int, int, int, int] | None = None
    fps = CONFIG.get("fps", 60)
    camera_index = CONFIG["camera_index"]
    acceptable_box_percent = CONFIG["acceptable_box_percent"]
    desired_width = CONFIG.get("frame_width", None)
    desired_height = CONFIG.get("frame_height", None)

    # Capture a frame from the source
    @abstractmethod
    def detect_person(self, frame) -> list:  # bboxes
        raise NotImplementedError()


def _detect_person_worker(
    model_class, frame_queue: multiprocessing.Queue, bbox_queue: multiprocessing.Queue
):
    model: ObjectModel = model_class()
    frame = True
    while frame is not None:
        try:
            frame = frame_queue.get(block=False)
            if frame is None:
                continue
            bboxes = model.detect_person(frame=frame)
            bbox_queue.put(bboxes)
        except Empty:
            continue
        except KeyboardInterrupt:
            bbox_queue.put(None)
            bbox_queue.close()
            return


# Abstract class for tracking
class Tracker:
    task: IterativeTask | None = None
    speaker_bbox: tuple[int, int, int, int] | None = None
    fps = CONFIG.get("fps", 60)
    camera_index = CONFIG["camera_index"]
    acceptable_box_percent = CONFIG["acceptable_box_percent"]
    desired_width: int | None = CONFIG.get("frame_width", None)
    desired_height: int | None = CONFIG.get("frame_height", None)
    model = None
    _bboxes: list | None = None
    _frame = None

    def __init__(
        self,
        model=None,
        scheduler: Scheduler | None = None,
        source: str | None = None,
        video_buffer_size=1,
    ):
        self.cap = cv2.VideoCapture(source or self.camera_index)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, video_buffer_size)  # Reduce buffer size
        self.frame_delay = 1000 / self.fps
        self.scheduler = scheduler
        self.model = model
        self.start_video()

    def start_detection_process(self):
        if hasattr(self, "_detection_process") and self._detection_process is not None:
            return  # Already running

        self._frame_queue = multiprocessing.Queue(maxsize=1)
        self._bbox_queue = multiprocessing.Queue(maxsize=1)
        self._detection_process = multiprocessing.Process(
            target=_detect_person_worker,
            args=(self.model, self._frame_queue, self._bbox_queue),
            daemon=True,
        )
        self._detection_process.start()
        add_termination_handler(self.stop)
        if self.scheduler:
            self.scheduler.set_timeout(10, self.poll_bboxes)
            self.scheduler.set_timeout(self.frame_delay, self.send_latest_frame)

    def poll_bboxes(self):
        try:
            self._bboxes = self._bbox_queue.get(block=False)
        except Empty:
            pass
        if (
            self._detection_process is not None
            and self._detection_process.is_alive()
            and self.scheduler
        ):
            self.scheduler.set_timeout(10, self.poll_bboxes)

    def send_latest_frame(self):
        if hasattr(self, "_frame") and self._frame is not None:
            try:
                self._frame_queue.put_nowait(self._frame)
            except Exception:
                pass
        if (
            self._detection_process is not None
            and self._detection_process.is_alive()
            and self.scheduler
        ):
            self.scheduler.set_timeout(self.frame_delay, self.send_latest_frame)

    def stop_detection_process(self):
        if hasattr(self, "_detection_process") and self._detection_process is not None:
            try:
                if hasattr(self, "_frame_queue"):
                    self._frame_queue.put_nowait(None)
                self._detection_process.join()
                self._bbox_queue.join_thread()
                self._frame_queue.join_thread()
            except Exception:
                pass
            self._detection_process = None

    def save_frame(self):
        hasFrame, frame = self.cap.read()
        if not hasFrame:
            return None
        self._frame = frame
        self.hasNewFrame = True
        return self.hasNewFrame, self._frame

    def get_frame_shape(self):
        self.hasNewFrame = False
        frame_height = self._frame.shape[0]
        frame_width = self._frame.shape[1]
        return (frame_height, frame_width)

    def get_bbox(self):
        return self._bboxes

    def draw_visuals(self, bounding_box, frame):
        """
        Draws all the visuals we need on the frame. Rectangles around bounding boxes, circles in the middle, acceptable box for director, red dot for speaker.

        Parameters:
        - bounding_box - bounding boxes from capture frame
        - frame - frame to draw on
        """
        # Draw the acceptable box
        frame_height = frame.shape[0]
        frame_width = frame.shape[1]
        (
            acceptable_box_left,
            acceptable_box_top,
            acceptable_box_right,
            acceptable_box_bottom,
        ) = calculate_acceptable_box(frame_width, frame_height)
        color = (0, 0, 255)  # Green color for the rectangle
        thickness = 2  # Thickness of the rectangle lines
        cv2.rectangle(
            frame,
            (acceptable_box_left, acceptable_box_top),
            (acceptable_box_right, acceptable_box_bottom),
            color,
            thickness,
        )

        for box in bounding_box:
            # Draw each bbox
            x1, y1, x2, y2 = box
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

            color = (0, 255, 0)  # Green color for the center point
            radius = 10  # Radius of the circle
            thickness = -1  # -1 fills the circle

            bbox_center_x, bbox_center_y = calculate_center_bbox(box)

            # Draw center of bounding box dot, this the value the commander is using
            cv2.circle(frame, (bbox_center_x, bbox_center_y), radius, color, thickness)

            # If speaker_bbox exists, draw line + distance
            if self.speaker_bbox is None:
                continue

            # Draw where the tracker is taking the color from - t-shirt area
            height = y2 - y1
            width = x2 - x1
            chest_start = y1 + int(height * 0.3)
            chest_end = y1 + int(height * 0.5)
            exclude_extra = x1 + int(width * 0.4)
            exclude_extra2 = x1 + int(width * 0.6)
            cv2.rectangle(
                frame,
                (exclude_extra, chest_start),
                (exclude_extra2, chest_end),
                (0, 150, 150),
                2,
            )

            # Red circle for speaker bbox
            cv2.circle(
                frame,
                calculate_center_bbox(self.speaker_bbox),
                radius,
                (0, 0, 255),
                thickness,
            )
        return frame

    def conv_cv2_frame_to_tkimage(self, frame):
        # Convert frame to tkinter image
        # Convert from BGR to RGB
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(frame_rgb)

        dim = (self.desired_width, self.desired_height)
        if self.desired_height is None:
            # Set desired dimensions (adjust these values as needed)
            new_width = self.desired_width or 500
            aspect_ratio = float(frame.shape[1]) / float(frame.shape[0])
            new_height = int(new_width / aspect_ratio)

            # Create the new dimensions tuple (width, height)
            dim = (new_width, new_height)
        assert dim[0] is not None and dim[1] is not None
        pil_image = pil_image.resize(dim, Image.Resampling.LANCZOS)  # pyright: ignore[reportArgumentType]
        return ImageTk.PhotoImage(image=pil_image)

    def create_imagetk(self, bboxes=None, frame=None):
        """This adds bounding box to the frame
        and returns the tkimage created.
        If the frame is supplied that frame will be used,
        else its latest internal frames will be used.
        If the bbox is not supplied the last stored frame will be used

        Returns:
            - bboxes
            - ImageTk.PhotoImage
        """
        frame = frame or self._frame
        bboxes = bboxes or self._bboxes
        if frame is None:
            return None
        if bboxes is not None:
            self.draw_visuals(bboxes, frame)
        return self.conv_cv2_frame_to_tkimage(frame)

    def start_video(self):
        assert self.scheduler is not None
        assert Tracker.task is None or not Tracker.task.running
        Tracker.task = self.scheduler.set_interval(self.frame_delay, self.save_frame)
        print("Video started")
        return Tracker.task

    def stop_video(self):
        """Stops the save frame capturing process"""
        print("Stopping video")
        if Tracker.task is not None:
            Tracker.task.cancel()

    def start(self):
        print("Starting Tracker")
        self.start_video()
        self.start_detection_process()

    def stop(self):
        print("Stopping Tracker")
        self.stop_video()
        self.stop_detection_process()

    def swap_model(self, new_model):
        """This will stop the current detection process and start a new process on the new model"""
        self.stop_detection_process()
        self.model = new_model
        self.start_detection_process()
