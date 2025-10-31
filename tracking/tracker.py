from abc import ABC, abstractmethod
from multiprocessing import Event, Lock, Process, Queue, shared_memory
from queue import Empty

import cv2
import numpy as np
from PIL import Image, ImageTk

from config import DEFAULT_CONFIG
from tkscheduler import IterativeTask, Scheduler
from utils import (
    add_termination_handler,
    calculate_acceptable_box,
    calculate_center_bbox,
)

SHARED_MEM_FRAME_NAME = "frame"


class ObjectModel(ABC):
    """
    This is a model class where it can handle turning image frame into bounding box
    The reason why this is separated is due to the fact that this will be running in a separate process.
    """

    speaker_bbox: tuple[int, int, int, int] | None = None
    fps = DEFAULT_CONFIG.get("fps", 60)
    camera_index = DEFAULT_CONFIG["camera_index"]
    acceptable_box_percent = DEFAULT_CONFIG["acceptable_box_percent"]
    desired_width = DEFAULT_CONFIG.get("frame_width", None)
    desired_height = DEFAULT_CONFIG.get("frame_height", None)

    # Capture a frame from the source
    @abstractmethod
    def detect_person(self, frame) -> list:  # bboxes
        raise NotImplementedError()


def _detect_person_worker(
    model_class, bbox_queue: Queue, stopper, frame_shape, frame_dtype, lock
) -> None:
    if model_class is None:
        print("Model was not found please pass a model into Tracker to run.")
        return
    shm = shared_memory.SharedMemory(name=SHARED_MEM_FRAME_NAME)
    frame = np.ndarray(frame_shape, dtype=frame_dtype, buffer=shm.buf)
    last_frame = np.zeros(frame_shape, frame_dtype)
    model: ObjectModel = model_class()
    try:
        while not stopper.is_set():
            np.copyto(last_frame, frame)  # visual artifact is not critical
            bboxes = model.detect_person(frame=frame)
            with lock:
                bbox_queue.put(bboxes)
    except KeyboardInterrupt:
        pass
    except ValueError:
        print("bbox_queue closed")
        pass
    finally:
        print("Model exiting cleanly...")
        shm.close()
        bbox_queue.close()
        print("Done")


# Class for handling video feed and object detection model usage
class Tracker:
    task: IterativeTask | None = None
    speaker_bbox: tuple[int, int, int, int] | None = None
    fps = DEFAULT_CONFIG.get("fps", 60)
    # camera_index = DEFAULT_CONFIG["camera_index"]
    acceptable_box_percent = DEFAULT_CONFIG["acceptable_box_percent"]
    desired_width: int | None = DEFAULT_CONFIG.get("frame_width", None)
    desired_height: int | None = DEFAULT_CONFIG.get("frame_height", None)
    model = None
    active_connection: str | None = None
    _bboxes: list | None = None
    _frames = dict()

    def __init__(
        self,
        connections,
        model=None,
        scheduler: Scheduler | None = None,
        video_buffer_size=1,
    ):
        self.connections = connections
        self.captures = dict()
        # self.cap = cv2.VideoCapture(source or self.camera_index)
        # self.cap.set(cv2.CAP_PROP_BUFFERSIZE, video_buffer_size)  # Reduce buffer size
        self.video_buffer_size = video_buffer_size
        self.frame_delay = 1000 / self.fps
        self.scheduler = scheduler
        self.model = model

    def add_capture(self, host: str, camera: str | int) -> None:
        """Adds a new video capture for a given host."""
        cap = cv2.VideoCapture(camera)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, self.video_buffer_size)  # Reduce buffer size
        self.captures[host] = cap
        if self.task is None or not self.task.running:
            self.start_video()

    def remove_capture(self, host: str) -> None:
        """Removes a video capture for a given host."""
        if host in self.captures:
            self.captures[host].release()
            self.captures.pop(host)
        if not self.captures:
            self.stop_video()

    def start_detection_process(self) -> None:
        if hasattr(self, "_detection_process") and self._detection_process is not None:
            return  # Already running

        img = self.save_frame()
        if img is None:
            print("Frame not found")
            return

        connection = img.get(self.active_connection, None)
        if connection is None:
            return
        _, frame = connection
        self.shape = frame.shape
        self.dtype = frame.dtype
        self.model_stopper = Event()
        self._frame_mem = shared_memory.SharedMemory(
            SHARED_MEM_FRAME_NAME, create=True, size=frame.nbytes
        )
        self._frame_buf = np.ndarray(self.shape, self.dtype, self._frame_mem.buf)
        # we only care about the latest bbox but I prefer to have more than 1 allocated size
        self._bbox_queue = Queue(maxsize=2)
        self.lock = Lock()
        self._detection_process = Process(
            target=_detect_person_worker,
            args=(
                self.model,
                self._bbox_queue,
                self.model_stopper,
                self.shape,
                self.dtype,
                self.lock,
            ),
            daemon=True,
        )
        self._detection_process.start()
        add_termination_handler(self.stop)
        if self.scheduler:
            self.scheduler.set_timeout(10, self.poll_bboxes)
            self.scheduler.set_timeout(self.frame_delay, self.send_latest_frame)

    def poll_bboxes(self) -> None:
        try:
            with self.lock:
                self._bboxes = self._bbox_queue.get(block=False)
        except ValueError:
            pass
        except Empty:
            pass
        if (
            self._detection_process is not None
            and self._detection_process.is_alive()
            and self.scheduler
        ):
            self.scheduler.set_timeout(10, self.poll_bboxes)
        elif self._detection_process is None:
            print("detection process is None; clearing internal bbox cache")
            self._bboxes = None

    def send_latest_frame(self) -> None:
        if hasattr(self, "_frames") and self._frames is not None:
            try:
                first_frame = self._frames[next(iter(self._frames))][1]
                np.copyto(self._frame_buf, first_frame)
            except Exception as e:
                print("Exception raise while copying frame to shared memory:", e)
                pass
        if (
            self._detection_process is not None
            and self._detection_process.is_alive()
            and self.scheduler
        ):
            self.scheduler.set_timeout(self.frame_delay, self.send_latest_frame)

    def stop_detection_process(self) -> bool:
        """Returns true if process properly closed"""
        if hasattr(self, "_detection_process") and self._detection_process is not None:
            try:
                self.model_stopper.set()
                self._detection_process.join()
                self._frame_mem.close()
                self._frame_mem.unlink()
                self._bbox_queue.close()
                self._bbox_queue.join_thread()
            except Exception as e:
                print("Exception occured:", e)
                return False
            self._detection_process = None
        self._bboxes = None
        return True

    def save_frame(self):
        if not self.captures:
            print("[WARNING] No captures available to save frame from, stopping video")
            self.stop_video()
            return None
        frames = dict()
        for host, cap in self.captures.items():
            hasFrame, frame = cap.read()
            if hasFrame:
                frames[host] = (True, frame)
        self._frames = frames
        return self._frames

    def get_frame_shape(self) -> tuple[int, int]:
        """returns: (height, weight)"""
        if self._frames is None:
            self.save_frame()
        assert self._frames
        self.hasNewFrame = False
        # TODO: figure out which video feed's frame shape is needed, probably by passing this function a hostname
        (_, frame) = self._frames[
            next(iter(self._frames))
        ]  # Temporarily just grab the first one
        frame_height = frame.shape[0]
        frame_width = frame.shape[1]
        return (frame_height, frame_width)

    def get_bbox(self):  # -> list[Any] | None:
        return self._bboxes

    def draw_visuals(self, bounding_box, frame):  # -> Any:
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

    def conv_cv2_frame_to_tkimage(self, frame) -> ImageTk.PhotoImage:
        """Convert frame to tkinter image"""
        frame_rgb = cv2.cvtColor(src=frame, code=cv2.COLOR_BGR2RGB)
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

    def create_imagetk(self, bboxes=None, frame=None) -> None | ImageTk.PhotoImage:
        """This adds bounding box to the frame
        and returns the tkimage created.
        If the frame is supplied that frame will be used,
        else its latest internal frames will be used.
        If the bbox is not supplied the last stored frame will be used

        Returns:
            - bboxes
            - ImageTk.PhotoImage
        """
        if frame is None:
            active_frame = self._frames.get(self.active_connection, None)
            frame = active_frame[1] if active_frame is not None else None
        bboxes = bboxes or self._bboxes
        if frame is None:
            return None
        # FIXME: this function needs to have bboxes be separated per connection
        # if bboxes is not None:
        #     self.draw_visuals(bboxes, frame)
        if frame is None:
            return None
        return self.conv_cv2_frame_to_tkimage(frame)

    def set_active_connection(self, connection: str) -> None:
        self.active_connection = connection

    def remove_active_connection(self) -> None:
        self.active_connection = None

    def start_video(self) -> IterativeTask:
        assert self.scheduler is not None
        assert Tracker.task is None or not Tracker.task.running
        Tracker.task = self.scheduler.set_interval(self.frame_delay, self.save_frame)
        print("Video started")
        return Tracker.task

    def stop_video(self) -> None:
        """Stops the save frame capturing process"""
        print("Stopping video")
        if Tracker.task is not None:
            Tracker.task.cancel()

    # NOTE: This function is never used, leaving it here for now
    def start(self) -> None:
        print("Starting Tracker")
        self.start_video()
        self.start_detection_process()

    def stop(self) -> bool:
        print("Stopping Tracker")
        self.stop_video()
        for _ in range(6):
            if self.stop_detection_process():
                return True
        return False

    def swap_model(self, new_model) -> None:
        """This will stop the current detection process and start a new process on the new model"""
        if not self.stop_detection_process():
            print("Failed to stop detection model")
            return
        self.model = new_model
        self.start_detection_process()
