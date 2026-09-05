from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from multiprocessing import Event, Process, Queue, shared_memory, synchronize
from multiprocessing.managers import SharedMemoryManager
from queue import Empty, Full
from typing import TYPE_CHECKING, Callable, Mapping

import cv2
import numpy as np
from loguru import logger

from src.logger import configure_logger
from src.observations.types import (
    FramePacket,
    LocalDetection,
    ObservationFrame,
    PersonObservation,
)
from src.tracking.types import (
    BBox,
    BBoxMapping,
    Frame,
    ObservationMapping,
)
from src.utils import add_termination_handler, remove_termination_handler

if TYPE_CHECKING:
    from src.connection.connection import (
        Connection,
        ConnectionCollection,
        ConnectionCollectionEvent,
    )
    from src.observations.replay import ObservationRecorder


class DetectionWaitingForModel(Exception):
    pass


class SendingFrameTooFast(Exception):
    pass


@dataclass
class FrameSizeData:
    original_size: Frame
    """original pixel size of the frame before resizing, used to calculate scale factor for bounding boxes"""
    size: Frame
    """pixel size of the frame after resizing"""
    scale_size: Frame
    """scale factor to convert bounding boxes from resized frame back to original frame size."""


type FrameSizeDeterminer = Callable[[np.ndarray, int, int | None], Frame]


@dataclass(frozen=True)
class SourceFrameMetadata:
    connection_id: str
    camera_id: str
    frame_sequence: int
    capture_timestamp: float
    x_offset: int
    width: int


@dataclass(frozen=True)
class DetectionBatch:
    sources: tuple[SourceFrameMetadata, ...]
    detections: tuple[LocalDetection, ...]


class ObjectModel(ABC):
    """
    This is a model class where it can handle turning image frame into bounding box
    The reason why this is separated is due to the fact that this will be running in a separate process.
    """

    # Capture a frame from the source
    @abstractmethod
    def detect_person(self, frame) -> list[LocalDetection | BBox]:
        raise NotImplementedError()

    @classmethod
    def determine_frame_size(
        cls, frame, inHeight: int | float, inWidth: int | float | None = None
    ) -> Frame:
        """
        Returns height by width tuple for resizing the frame before feeding it into the model.
        The default implementation maintains the aspect ratio of the original frame, and ensures that the dimensions are divisible by 32 to be compatible with YOLO models.
        The inHeight and inWidth parameters can be either absolute pixel values (int) or relative scale factors (float) compared to the original frame size.
        """
        frameHeight, frameWidth = frame.shape[:2]
        if inWidth is None:
            return int(inHeight), int((frameWidth / frameHeight) * inHeight)
        return int(inHeight), int(inWidth)

    @classmethod
    def resize_frame(
        cls,
        frame,
        inHeight,
        inWidth=None,
        frame_size_determiner: FrameSizeDeterminer | None = None,
        cvtColorCode=cv2.COLOR_BGR2RGB,
    ) -> tuple[np.ndarray, FrameSizeData]:
        frame_size_determiner = frame_size_determiner or cls.determine_frame_size
        frameOpenCV = frame.copy()
        original_size = frameOpenCV.shape[:2]
        frameHeight, frameWidth = original_size
        size = frame_size_determiner(frame, inHeight, inWidth)
        if any(s == 0 for s in size):
            raise ValueError(f"Invalid frame size determined: {size}")
        scale_size = (frameHeight / size[0], frameWidth / size[1])
        frameSmall = cv2.resize(frameOpenCV, size[::-1])
        return cv2.cvtColor(frameSmall, cvtColorCode), FrameSizeData(
            original_size=original_size, size=size, scale_size=scale_size
        )

    @classmethod
    def fix_bbox_scale(cls, bbox: BBox, frame_size_data: FrameSizeData) -> BBox:
        scaleHeight, scaleWidth = frame_size_data.scale_size
        x1, y1, x2, y2 = bbox
        return (
            x1 * scaleWidth,
            y1 * scaleHeight,
            x2 * scaleWidth,
            y2 * scaleHeight,
        )

    @classmethod
    def xywh_to_xyxy(cls, bbox: BBox) -> BBox:
        x, y, w, h = bbox
        return (x, y, x + w, y + h)


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
    frame_order: list[tuple[str, int]] = []
    model: ObjectModel.__class__ | None
    _smm: SharedMemoryManager
    _detection_process: Process | None = None
    _bbox_queue: Queue[DetectionBatch | None]
    _frame_metadata_queue: Queue[tuple[SourceFrameMetadata, ...]]
    _model_stopper: synchronize.Event
    _frame_ready_event: synchronize.Event
    _frame_memory: shared_memory.SharedMemory | None = None

    def __init__(
        self,
        model: ObjectModel.__class__ | None,
        connections: ConnectionCollection,
        smm: SharedMemoryManager = SharedMemoryManager(),
        observation_recorder: ObservationRecorder | None = None,
    ):
        self.model = model
        self.connections = connections
        self.connections.add_listener(self.on_connections_update)
        self.frame_order = self._create_frame_order(connections)
        self._latest_observations: ObservationMapping = {}
        self._last_sent_sequences: dict[str, int] = {}
        self._smm = smm
        self.observation_recorder = observation_recorder
        self._smm.start()

    def start(self):
        if self.model is None:
            logger.error("Model was not found please pass a model into Tracker to run.")
            return
        self.waiting_startup = True
        self._last_sent_sequences = {}
        self._bbox_queue = Queue(maxsize=2)
        self._frame_metadata_queue = Queue(maxsize=1)
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
                self._frame_metadata_queue,
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
            self._frame_metadata_queue.close()
            self._detection_process.join()
            self._bbox_queue.join_thread()
            self._frame_metadata_queue.join_thread()
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

    def on_connections_update(self, event: ConnectionCollectionEvent, *_):  # pyright: ignore[reportIncompatibleMethodOverride]
        from src.connection.connection import (
            ConnectionCollectionEvent,
        )

        if event in (
            ConnectionCollectionEvent.ADDED,
            ConnectionCollectionEvent.REMOVED,
        ):
            self.reset_frame_order()

    def send_input(self, packets: Mapping[str, FramePacket] | None = None):
        if self._frame_ready_event.is_set():
            if not self.waiting_startup:
                raise SendingFrameTooFast(
                    "Previous frame is still being processed, skipping sending new frame to detector."
                )
            raise DetectionWaitingForModel(
                "Detection process is still starting up, please wait and try again."
            )
        self._frame_buf.fill(0)
        sources: list[SourceFrameMetadata] = []
        for index, (host, x_offset) in enumerate(self.frame_order):
            video_conn = self.connections[host].video_connection
            packet = (
                packets.get(host)
                if packets is not None
                else video_conn.get_latest_packet()
                if video_conn is not None
                else None
            )
            if (
                packet is None
                or self._last_sent_sequences.get(host) == packet.frame_sequence
            ):
                continue
            expected_width = (
                self.frame_order[index + 1][1] - x_offset
                if index + 1 < len(self.frame_order)
                else self._frame_buf.shape[1] - x_offset
            )
            copy_height = min(packet.image.shape[0], self._frame_buf.shape[0])
            copy_width = min(packet.image.shape[1], expected_width)
            np.copyto(
                self._frame_buf[:copy_height, x_offset : x_offset + copy_width],
                packet.image[:copy_height, :copy_width],
            )
            sources.append(
                SourceFrameMetadata(
                    connection_id=host,
                    camera_id=packet.camera_id,
                    frame_sequence=packet.frame_sequence,
                    capture_timestamp=packet.capture_timestamp,
                    x_offset=x_offset,
                    width=expected_width,
                )
            )

        if not sources:
            logger.warning(
                f"No frames available to update frame buffer. {self.frame_order=}"
            )
            raise SendingFrameTooFast("No frames available to update frame buffer.")
        self._frame_metadata_queue.put_nowait(tuple(sources))
        self._last_sent_sequences.update(
            {source.connection_id: source.frame_sequence for source in sources}
        )
        self._frame_ready_event.set()

    def get_bboxes(self) -> BBoxMapping:
        """Returns a dictionary mapping hostnames to lists of bounding boxes (x1, y1, x2, y2)

        Throws Empty if no bounding boxes are detected.
        Throws ValueError if the bbox queue is closed.
        """
        try:
            batch: DetectionBatch | None = self._bbox_queue.get(block=False)
        except (ValueError, Empty) as e:
            if self.waiting_startup:
                raise DetectionWaitingForModel(
                    "Detection process is still starting up, please wait and try again."
                )
            raise e
        if batch is None:
            if self.waiting_startup:
                raise DetectionWaitingForModel(
                    "Detection process is still starting up, please wait and try again."
                )
            raise Empty("No bounding boxes detected.")
        if self.waiting_startup:
            self.waiting_startup = False
            logger.info("Model loaded, starting to poll bounding boxes.")

        observations_by_host: ObservationMapping = {
            host: [] for host, _ in self.frame_order
        }
        for detection in batch.detections:
            x1, y1, x2, y2 = detection.bounding_box
            cx = (x1 + x2) // 2
            source = next(
                (
                    source
                    for source in batch.sources
                    if source.x_offset <= cx < source.x_offset + source.width
                ),
                None,
            )
            if source is None:
                continue
            source_bbox = (
                max(0, x1 - source.x_offset),
                y1,
                max(0, x2 - source.x_offset),
                y2,
            )
            observations_by_host[source.connection_id].append(
                PersonObservation(
                    camera_id=source.camera_id,
                    frame_sequence=source.frame_sequence,
                    capture_timestamp=source.capture_timestamp,
                    bounding_box=source_bbox,
                    detection_confidence=detection.confidence,
                    local_track_id=detection.local_track_id,
                )
            )

        bboxes_by_host: BBoxMapping = {
            host: [] for host, _ in self.frame_order
        }
        for host, observations in observations_by_host.items():
            self.connections[host].set_observations(observations)
        for source in batch.sources:
            observations = observations_by_host[source.connection_id]
            bboxes_by_host[source.connection_id] = [
                observation.bounding_box for observation in observations
            ]
            if self.observation_recorder is not None:
                self.observation_recorder.record(
                    ObservationFrame(
                        camera_id=source.camera_id,
                        frame_sequence=source.frame_sequence,
                        capture_timestamp=source.capture_timestamp,
                        observations=tuple(observations),
                    )
                )
        self._latest_observations = observations_by_host
        return bboxes_by_host

    def get_observations(self) -> ObservationMapping:
        """Return the latest rich observations without consuming detector output."""

        return {
            host: list(observations)
            for host, observations in self._latest_observations.items()
        }

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
        frame_order = []
        for host, conn in connections.items():
            video_conn = conn.video_connection
            if video_conn is None or (shape := video_conn.shape) is None:
                continue
            max_height = max(max_height, shape[0])
            frame_order.append((host, total_width))
            total_width = total_width + shape[1]
        return (max_height, total_width, 3)

    @staticmethod
    def _create_frame_order(connections: ConnectionCollection):
        frame_order = []
        total_width = 0
        max_height = 0
        for host, conn in connections.items():
            video_conn = conn.video_connection
            if video_conn is None or (shape := video_conn.shape) is None:
                continue
            max_height = max(max_height, shape[0])
            frame_order.append((host, total_width))
            total_width = total_width + shape[1]
        return frame_order

    def reset_frame_order(self):
        self.frame_order = self._create_frame_order(self.connections)
        if self._detection_process is not None and self._detection_process.is_alive():
            if len(self.connections) == 0:
                logger.debug(
                    "No more connections available, stopping detection process..."
                )
                self.stop()
                return
            logger.debug("Restarting detection process to update frame order...")
            self.restart()

    @staticmethod
    def _detect_person_worker(
        model_class,
        bbox_queue: Queue,
        frame_metadata_queue: Queue,
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
                # Consume metadata before clearing the event so the producer cannot
                # overwrite the single shared frame slot first.
                raw_frame = np.copy(frame)
                sources = frame_metadata_queue.get()
                frame_ready_event.clear()
                try:
                    raw_detections = model.detect_person(frame=raw_frame)
                    detections = tuple(
                        detection
                        if isinstance(detection, LocalDetection)
                        else LocalDetection(bounding_box=tuple(detection))
                        for detection in raw_detections
                    )
                except Exception as e:
                    logger.error(f"Error during detection: {e}")
                    continue
                if bbox_queue.full():
                    logger.warning("bbox_queue is full, deleting oldest output")
                    try:
                        bbox_queue.get_nowait()
                    except Empty:
                        pass  # This sometimes happens just ignore it since we just wanted to make space in the queue
                try:
                    bbox_queue.put_nowait(
                        DetectionBatch(sources=sources, detections=detections)
                    )
                except Full:
                    logger.warning("bbox_queue is full, skipping frame")
            else:
                logger.info("Stop event received, exiting detection loop.")
        except KeyboardInterrupt:
            logger.info("Detection process received KeyboardInterrupt, exiting.")
        except ValueError:
            logger.error("bbox_queue closed")
