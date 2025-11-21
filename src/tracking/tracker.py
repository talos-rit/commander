from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from multiprocessing import Event, Process, Queue, shared_memory
from multiprocessing.managers import SharedMemoryManager
from queue import Empty, Full

import cv2
import numpy as np
from PIL import Image, ImageTk

from src.config import load_config, load_default_config
from src.manual_interface import ConnectionData
from src.tkscheduler import IterativeTask, Scheduler
from src.utils import (
    add_termination_handler,
    calculate_acceptable_box,
    calculate_center_bbox,
    remove_termination_handler,
)

SHARED_MEM_FRAME_NAME = "frame"
POLL_BBOX_CYCLE_INTERVAL_MS = 10


class ObjectModel(ABC):
    """
    This is a model class where it can handle turning image frame into bounding box
    The reason why this is separated is due to the fact that this will be running in a separate process.
    """

    # Capture a frame from the source
    @abstractmethod
    def detect_person(self, frame) -> list:  # bboxes
        raise NotImplementedError()


def _detect_person_worker(
    model_class,
    bbox_queue: Queue,
    stopper,
    frame_mem: shared_memory.SharedMemory,
    frame_shape,
    frame_dtype,
) -> None:
    if model_class is None:
        print("Model was not found please pass a model into Tracker to run.")
        return
    frame = np.ndarray(frame_shape, dtype=frame_dtype, buffer=frame_mem.buf)
    model: ObjectModel = model_class()
    try:
        while not stopper.is_set():
            bboxes = model.detect_person(frame=np.copy(frame))
            try:
                bbox_queue.put_nowait(bboxes)
            except Full:
                pass
    except KeyboardInterrupt:
        pass
    except ValueError:
        print("bbox_queue closed")


@dataclass
class VideoConnection:
    src: str | int
    fps: int = field(default=10)
    shape: tuple | None = field(default=None)
    dtype: np.dtype | None = field(default=None)
    cap: cv2.VideoCapture | None = field(default=None, repr=False)
    task: IterativeTask | None = field(default=None, repr=False)
    video_buffer_size: int = field(default=1)
    _term: int | None = field(default=None)

    def __post_init__(self):
        if self.cap is None:
            source = None
            try:
                source = int(self.src)
            except ValueError:
                source = self.src
            self.cap = cv2.VideoCapture(source)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, self.video_buffer_size)
            self._term = add_termination_handler(self.close)
        frame = None
        for _ in range(6):
            ret, frame = self.cap.read()
            if ret and frame is not None:
                break
        else:
            print("Unable to pull frame from camera")
            return
        self.shape = frame.shape
        self.dtype = frame.dtype

    @property
    def frame(self) -> np.ndarray | None:
        if self.cap is not None:
            _, frame = self.cap.read()
            return frame

    def close(self):
        if self.cap is not None:
            self.cap.release()
        if self._term is not None:
            remove_termination_handler(self._term)
            self._term = None


# Class for handling video feed and object detection model usage
class Tracker:
    speaker_bbox: tuple[int, int, int, int] | None = None
    config: dict = load_config()
    default_config: dict = load_default_config()
    max_fps = 1  # this will be set dynamically based on captures
    frame_delay: float = 0.0  # same as above
    model = None
    captures: dict[str, VideoConnection] = dict()
    frame_order: list[tuple[str, int]] = list()  # (host, frame x location)[]
    active_connection: str | None = None
    _bboxes: dict[str, list] = dict()
    _frame_buf: np.ndarray
    _bbox_queue: Queue
    is_detection_running: bool = False
    _detection_process: Process | None = None
    _term: int | None = None
    _send_frame_task: IterativeTask | None = None
    _poll_bbox_task: IterativeTask | None = None
    _smm: SharedMemoryManager | None = None

    def __init__(
        self,
        connections: dict[str, ConnectionData] = dict(),
        model=None,
        scheduler: Scheduler | None = None,
        video_buffer_size=1,
    ):
        self.video_buffer_size = video_buffer_size
        self.scheduler = scheduler
        self.model = model
        self._smm = SharedMemoryManager()
        self._smm.start()
        for host, conn in connections.items():
            self.max_fps = max(self.max_fps, conn.fps)
            frame_shape = self.add_capture(
                host, conn.camera, conn.fps, write_config=False
            )
            conn.set_frame_shape(frame_shape)
        self.frame_delay = 1000 / self.max_fps

    def add_capture(
        self, host: str, camera: str | int, fps: int, write_config: bool
    ) -> tuple | None:
        """Adds a new video capture for a given host.
        If the detection process is running this will restart it.
        Parameters:
        - host: unique identifier for the video source
        - camera: video source (file path or camera index)
        - fps: frames per second for the video source
        Returns:
        - frame_shape: the frame shape of the video source
        """
        restart = False
        if self._detection_process is not None:
            restart = True
            self.stop_detection_process()
        elif self.model is not None:
            restart = True
        # if the detection process was not running because there were no captures, start after adding the first capture
        conn = VideoConnection(src=camera, fps=fps)
        self.captures[host] = conn
        self.frame_order.append((host, 0))
        if write_config:
            self.config = load_config()
        # self.update_max_fps()
        if restart:
            self.start_detection_process()
        return conn.shape

    def remove_capture(self, host: str | None = None) -> None:
        """Releases video capture for a given host if not all video capture is closed."""
        if host is None:
            for host, cap in self.captures.items():
                cap.close()
            return
        if host in self.captures:
            self.captures[host].close()
        self.frame_order = [fo for fo in self.frame_order if fo[0] != host]
        del self.captures[host]
        if not self.captures:
            self.stop_detection_process()
        # self.update_max_fps()

    def update_max_fps(self) -> None:
        """Updates the max fps based on current captures."""
        self.max_fps = 0
        for conn in self.captures.values():
            self.max_fps = max(self.max_fps, conn.fps)
        self.frame_delay = 1000 / self.max_fps

    def start_detection_process(self) -> None:
        if self._detection_process is not None:
            return  # Already running
        assert self._smm is not None
        print("Starting detection process...")
        self.is_detection_running = True
        total_shape = self.get_total_frame_shape()
        total_nbytes = self.get_nbytes_from_total_shape(total_shape)

        self.model_stopper = Event()
        # idk why but gc keeps deleting shared memory without me holding reference via "self."
        self._frame_memory = self._smm.SharedMemory(size=total_nbytes)
        self._frame_buf = np.ndarray(total_shape, np.uint8, self._frame_memory.buf)
        # we only care about the latest bbox but I prefer to have more than 1 allocated size
        self._bbox_queue = Queue(maxsize=2)
        self._detection_process = Process(
            target=_detect_person_worker,
            args=(
                self.model,
                self._bbox_queue,
                self.model_stopper,
                self._frame_memory,
                total_shape,
                np.uint8,
            ),
            daemon=True,
        )
        self._detection_process.start()
        self._term = add_termination_handler(self.stop)
        print("Detection process started.")
        if self.scheduler:
            self._poll_bbox_task = self.scheduler.set_interval(
                self.frame_delay, self.poll_bboxes
            )
            self._send_frame_task = self.scheduler.set_interval(
                self.frame_delay, self.send_latest_frame
            )

    def poll_bboxes(self) -> None:
        print("Polling bounding boxes from detection process")
        raw_bboxes: None | list[tuple[int, int, int, int]] = None

        try:
            raw_bboxes = self._bbox_queue.get(block=False)
        except ValueError:
            return
        except Empty:
            return
        assert raw_bboxes is not None

        bboxes_by_host: dict = {host: [] for host, _ in self.frame_order}

        if 1 == len(self.frame_order):
            (host, _) = self.frame_order[0]
            self._bboxes = {host: raw_bboxes}
            return

        for x1, y1, x2, y2 in raw_bboxes:
            cx = (x1 + x2) // 2

            for index, (host, dx) in enumerate(self.frame_order):
                if index == len(self.frame_order) - 1:
                    bboxes_by_host[host].append(
                        [max(0, x1 - dx), y1, max(0, x2 - dx), y2]
                    )
                    continue
                (_, dx_next) = self.frame_order[index + 1]
                if cx >= dx and cx < dx_next:
                    bboxes_by_host[host].append(
                        [max(0, x1 - dx), y1, max(0, x2 - dx), y2]
                    )

        self._bboxes = bboxes_by_host

    def get_total_frame_shape(self):
        """
        Merges all of the frames side by side in a predictive manner.
        """
        total_width = 0
        max_height = 0
        self.frame_order = list()
        for host, vid in self.captures.items():
            shape = vid.shape
            if shape is None:
                continue
            max_height = max(max_height, shape[0])
            self.frame_order.append((host, total_width))
            total_width = total_width + shape[1]
        return (max_height, total_width, 3)

    def get_nbytes_from_total_shape(self, shape):
        """Given total frame shape, calculate nbytes for shared memory.

        Accepts shape in either (height, width) or (height, width, channels).
        Assumes 8-bit per channel (np.uint8) which is standard for OpenCV frames.
        """
        if shape is None:
            return 0
        if len(shape) == 2:
            height, width = shape
            channels = 3
        elif len(shape) == 3:
            height, width, channels = shape
        else:
            raise ValueError(f"Unsupported shape length: {len(shape)}")

        try:
            h = int(height)
            w = int(width)
            c = int(channels)
        except (TypeError, ValueError):
            raise ValueError("Shape elements must be integers")

        return h * w * c * np.dtype(np.uint8).itemsize

    def send_latest_frame(self) -> None:
        if 1 == len(self.frame_order):
            (host, _) = self.frame_order[0]
            vid = self.captures[host]
            new_frame = vid.frame
            if new_frame is not None:
                np.copyto(self._frame_buf, new_frame)
            return

        frames = [self.captures[host].frame for host, _ in self.frame_order]
        frames = [f for f in frames if f is not None]
        if len(frames) == 0:
            print("No frames available to update frame buffer.")
            return
        # Compare heights of frames and padd the bottom to the smaller ones to match the largest height
        max_height = max(frame.shape[0] for frame in frames)
        resized_frames = [
            frame
            if frame.shape[0] == max_height
            else np.pad(
                frame,
                ((0, max_height - frame.shape[0]), (0, 0), (0, 0)),
                mode="constant",
                constant_values=0,
            )
            for frame in frames
        ]
        hstack = np.hstack(resized_frames)
        np.copyto(self._frame_buf, hstack)

    def stop_detection_process(self) -> bool:
        """Returns true if process properly closed"""
        if not self.is_detection_running:
            return True
        assert self._smm is not None
        self.is_detection_running = False
        self._send_frame_task.cancel() if self._send_frame_task else None
        self._poll_bbox_task.cancel() if self._poll_bbox_task else None
        self._bboxes = dict()
        if self._detection_process is not None:
            try:
                self.model_stopper.set()
                self._detection_process.join()
                self._bbox_queue.close()
                self._bbox_queue.join_thread()
                self.model_stopper.clear()
            except Exception as e:
                print("Exception occured:", e)
                return False
            self._detection_process = None
            print("Detection process stopped.")
        return True

    def get_frame_shape(self, host):  # -> tuple[Any, ...] | None:
        """returns: (height, weight)"""
        conn = self.captures[host]
        if conn is not None:
            return conn.shape

    def get_bboxes(self):
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

    def conv_cv2_frame_to_tkimage(self, frame) -> ImageTk.PhotoImage | None:
        """Convert frame to tkinter image"""
        # Load config values
        if self.active_connection in self.config:
            config_data = self.config[self.active_connection]
        else:
            config_data = self.default_config
        desired_height: int | None = config_data.get("frame_height", None)
        desired_width: int | None = config_data.get("frame_width", None)
        if frame is None:
            return None
        frame_rgb = cv2.cvtColor(src=frame, code=cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(frame_rgb)

        dim = (desired_width, desired_height)
        if desired_height is None:
            # Set desired dimensions (adjust these values as needed)
            new_width = desired_width or 500
            aspect_ratio = float(frame.shape[1]) / float(frame.shape[0])
            new_height = int(new_width / aspect_ratio)

            # Create the new dimensions tuple (width, height)
            dim = (new_width, new_height)
        assert dim[0] is not None and dim[1] is not None
        pil_image = pil_image.resize(dim, Image.Resampling.LANCZOS)  # pyright: ignore[reportArgumentType]
        return ImageTk.PhotoImage(image=pil_image)

    def create_imagetk(self) -> None | ImageTk.PhotoImage:
        """This adds bounding box to the frame
        and returns the tkimage created.
        If the frame is supplied that frame will be used,
        else its latest internal frames will be used.
        If the bbox is not supplied the last stored frame will be used

        Returns:
            - bboxes
            - ImageTk.PhotoImage
        """
        if self.active_connection is None:
            return
        cap = self.captures.get(self.active_connection, None)
        if cap is None:
            return
        active_frame = cap.frame
        if self.active_connection is not None:
            bboxes = self._bboxes.get(self.active_connection, None)
            if bboxes is not None:
                self.draw_visuals(bboxes, active_frame)
        return self.conv_cv2_frame_to_tkimage(active_frame)

    def set_active_connection(self, connection: str) -> None:
        self.active_connection = connection

    def remove_active_connection(self) -> None:
        self.active_connection = None

    def stop(self) -> bool:
        if self._term is not None:
            remove_termination_handler(self._term)
            self._term = None
        self.remove_capture()
        for _ in range(6):
            if self.stop_detection_process():
                self._smm.shutdown() if self._smm is not None else None
                self._smm = None
                return True
        return False

    def swap_model(self, new_model) -> None:
        """This will stop the current detection process and start a new process on the new model"""
        if not self.stop_detection_process():
            print("Failed to stop detection model")
            return
        self.model = new_model
        if (
            self.captures and self.model is not None
        ):  # do not start detection process if there are no captures, or if model is None
            self.start_detection_process()
