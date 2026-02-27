from abc import ABC, abstractmethod
from multiprocessing import Event, Process, Queue, shared_memory, synchronize
from multiprocessing.managers import SharedMemoryManager
from queue import Empty, Full

import numpy as np
from loguru import logger

from ..connection.connection import (
    Connection,
    ConnectionCollection,
    ConnectionCollectionEvent,
)
from ..logger import configure_logger
from ..utils import add_termination_handler, remove_termination_handler

type BBoxMapping = dict[str, list[tuple[int, int, int, int]]]


class DetectionWaitingForModel(Exception):
    pass


class ObjectModel(ABC):
    """
    This is a model class where it can handle turning image frame into bounding box
    The reason why this is separated is due to the fact that this will be running in a separate process.
    """

    # Capture a frame from the source
    @abstractmethod
    def detect_person(self, frame) -> list:  # bboxes
        raise NotImplementedError()


class DetectorInterface(ABC):
    @abstractmethod
    def start(self):
        raise NotImplementedError()

    @abstractmethod
    def stop(self):
        raise NotImplementedError()

    @abstractmethod
    def on_connections_update(
        self, event: ConnectionCollectionEvent, hostname: str, connection: Connection
    ):
        raise NotImplementedError()

    @abstractmethod
    def send_input(self):
        raise NotImplementedError()

    @abstractmethod
    def get_bboxes(self) -> BBoxMapping:
        raise NotImplementedError()


class Detector(DetectorInterface):
    connections: ConnectionCollection
    frame_order: list[tuple[str, int]] = list()
    model: ObjectModel.__class__ | None
    _smm: SharedMemoryManager
    _detection_process: Process | None = None
    _bbox_queue: Queue
    _model_stopper: synchronize.Event
    _frame_ready_event: synchronize.Event
    _frame_memory: shared_memory.SharedMemory | None = None

    def __init__(
        self,
        model: ObjectModel.__class__ | None,
        connections: ConnectionCollection,
        smm: SharedMemoryManager = SharedMemoryManager(),
    ):
        self.model = model
        self.connections = connections
        self.connections.add_listener(self.on_connections_update)
        self.frame_order = self._create_frame_order(connections)
        self._smm = smm
        self._smm.start()

    def start(self):
        if self.model is None:
            logger.error("Model was not found please pass a model into Tracker to run.")
            return
        self.waiting_startup = True
        self._bbox_queue = Queue(maxsize=2)
        self._model_stopper = Event()
        self._frame_ready_event = Event()
        total_shape = self.total_frame_shape(self.connections)
        # idk why but gc keeps deleting shared memory without me holding reference via "self."
        self._frame_memory = self._smm.SharedMemory(size=self.total_nbytes())
        self._frame_buf = np.ndarray(
            total_shape, np.uint8, buffer=self._frame_memory.buf
        )

        if self._detection_process is not None and self._detection_process.is_alive():
            logger.warning("Detection process is already running.")
            return

        self._detection_process = Process(
            target=self._detect_person_worker,
            args=(
                self.model,
                self._bbox_queue,
                self._model_stopper,
                self._frame_ready_event,
                self._frame_memory,
                total_shape,
                np.uint8,
            ),
            daemon=True,
        )
        self._term = add_termination_handler(self.kill)
        self._detection_process.start()
        logger.info("Firing up model...")

    def stop(self):
        self.connections.clear_bboxes()
        if self._detection_process is None or not self._detection_process.is_alive():
            self._detection_process = None
            self._term = None
            return logger.warning("Detection process is already stopped.")
        try:
            self._frame_ready_event.clear()
            self._model_stopper.set()
            self._bbox_queue.close()
            self._detection_process.join()
            self._bbox_queue.join_thread()
        except Exception as e:
            logger.error(f"Exception occured: {e}")
            return False
        self._detection_process = None
        if self._term is not None:
            remove_termination_handler(self._term)
            self._term = None
        logger.debug("Detection process stopped.")
        return True

    def kill(self):
        """Cleans up all resources used by the detection process, including shared memory and termination handlers.
        Only run this at the end of the program when the tracker will no longer be used, as this is not reversible without restarting the program.
        """
        if self.is_running():
            self.stop()
        self._smm.shutdown()

    def restart(self):
        if self._detection_process is None or not self._detection_process.is_alive():
            logger.warning("Detection process is not running")
            return False
        self.waiting_startup = True
        self.stop()
        self.start()
        return True

    def total_nbytes(self):
        shape = self.total_frame_shape(self.connections)
        return shape[0] * shape[1] * shape[2] * np.dtype(np.uint8).itemsize

    def on_connections_update(self, event: ConnectionCollectionEvent, *args):
        if event in (
            ConnectionCollectionEvent.ADDED,
            ConnectionCollectionEvent.REMOVED,
        ):
            self.reset_frame_order()

    def send_input(self):
        if self._frame_ready_event.is_set():
            if not self.waiting_startup:
                logger.warning(
                    "Previous frame is still being processed, skipping sending new frame to detector."
                )
            return
        if 1 == len(self.frame_order):
            (host, _) = self.frame_order[0]
            self.new_frame = self.connections[host].video_connection.get_frame()
            if self.new_frame is not None and not self._frame_ready_event.is_set():
                np.copyto(self._frame_buf, self.new_frame)
                self._frame_ready_event.set()
            return

        frames = [
            self.connections[host].video_connection.get_frame()
            for host, _ in self.frame_order
        ]
        frames = [f for f in frames if f is not None]
        if len(frames) == 0:
            logger.warning(
                f"No frames available to update frame buffer. {frames=} {self.frame_order=}"
            )
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
        self._frame_ready_event.set()

    def get_bboxes(self) -> BBoxMapping:
        """Returns a dictionary mapping hostnames to lists of bounding boxes (x1, y1, x2, y2)

        Throws Empty if no bounding boxes are detected.
        Throws ValueError if the bbox queue is closed.
        """
        try:
            raw_bboxes: None | list[tuple[int, int, int, int]] = self._bbox_queue.get(
                block=False
            )
        except (ValueError, Empty) as e:
            if self.waiting_startup:
                raise DetectionWaitingForModel(
                    "Detection process is still starting up, please wait and try again."
                )
            raise e
        if raw_bboxes is None:
            if self.waiting_startup:
                raise DetectionWaitingForModel(
                    "Detection process is still starting up, please wait and try again."
                )
            raise Empty("No bounding boxes detected.")
        if self.waiting_startup:
            self.waiting_startup = False
            logger.info("Model loaded, starting to poll bounding boxes.")

        if 1 == len(self.frame_order):
            (host, _) = self.frame_order[0]
            self.connections[host].set_bboxes(raw_bboxes)
            return {host: raw_bboxes}

        bboxes_by_host: BBoxMapping = {host: [] for host, _ in self.frame_order}
        for x1, y1, x2, y2 in raw_bboxes:
            cx = (x1 + x2) // 2

            for index, (host, dx) in enumerate(self.frame_order):
                if index == len(self.frame_order) - 1:
                    bboxes_by_host[host].append(
                        (max(0, x1 - dx), y1, max(0, x2 - dx), y2)
                    )
                    continue
                (_, dx_next) = self.frame_order[index + 1]
                if cx >= dx and cx < dx_next:
                    bboxes_by_host[host].append(
                        (max(0, x1 - dx), y1, max(0, x2 - dx), y2)
                    )

        for host, bboxes in bboxes_by_host.items():
            self.connections[host].set_bboxes(bboxes)
        return bboxes_by_host

    def is_running(self):
        return (
            self._detection_process is not None and self._detection_process.is_alive()
        )

    def set_model(self, model: ObjectModel.__class__ | None):
        self.model = model
        logger.info(f"Model set to {model.__name__ if model is not None else 'None'}")
        if self.is_running() and model is not None:
            self.restart()
        if self.is_running() and model is None:
            self.stop()
        return self.model

    @staticmethod
    def total_frame_shape(connections: ConnectionCollection):
        total_width = 0
        max_height = 0
        frame_order = list()
        for host, conn in connections.items():
            if (shape := conn.video_connection.shape) is None:
                continue
            max_height = max(max_height, shape[0])
            frame_order.append((host, total_width))
            total_width = total_width + shape[1]
        return (max_height, total_width, 3)

    @staticmethod
    def _create_frame_order(connections: ConnectionCollection):
        frame_order = list()
        total_width = 0
        max_height = 0
        for host, conn in connections.items():
            if (shape := conn.video_connection.shape) is None:
                continue
            max_height = max(max_height, shape[0])
            frame_order.append((host, total_width))
            total_width = total_width + shape[1]
        return frame_order

    def reset_frame_order(self):
        self.frame_order = self._create_frame_order(self.connections)
        if self._detection_process is not None and self._detection_process.is_alive():
            logger.debug("Restarting detection process to update frame order...")
            self.restart()

    @staticmethod
    def _detect_person_worker(
        model_class,
        bbox_queue: Queue,
        stopper,
        frame_ready_event: synchronize.Event,
        frame_mem: shared_memory.SharedMemory,
        frame_shape,
        frame_dtype,
    ) -> None:
        configure_logger(process_name="detection_process", remove_existing=True)
        logger.info("Detection process started.")
        if model_class is None:
            logger.error("Model was not found please pass a model into Tracker to run.")
            return
        frame = np.ndarray(frame_shape, dtype=frame_dtype, buffer=frame_mem.buf)
        model: ObjectModel = model_class()
        try:
            while not stopper.is_set():
                if not frame_ready_event.wait(0.1):
                    logger.debug("No new frame received, continuing to wait...")
                    continue
                # Not clear immediately to make a copy here safely
                raw_frame = np.copy(frame)
                frame_ready_event.clear()
                bboxes = model.detect_person(frame=raw_frame)
                if bbox_queue.full():
                    logger.warning("bbox_queue is full, deleting oldest output")
                    try:
                        bbox_queue.get_nowait()
                    except Empty:
                        pass  # This sometimes happens just ignore it since we just wanted to make space in the queue
                try:
                    bbox_queue.put_nowait(bboxes)
                except Full:
                    logger.warning("bbox_queue is full, skipping frame")
            else:
                logger.info("Stop event received, exiting detection loop.")
        except KeyboardInterrupt:
            logger.info("Detection process received KeyboardInterrupt, exiting.")
            pass
        except ValueError:
            logger.error("bbox_queue closed")
