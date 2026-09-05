import threading
from multiprocessing import shared_memory
from io import StringIO
from itertools import islice
from pathlib import Path
from queue import Queue
from types import SimpleNamespace

import numpy as np

from src.connection.connection import VideoConnection
from src.observations import (
    FramePacket,
    LocalDetection,
    ObservationFrame,
    ObservationRecorder,
    ObservationReplay,
    PersonObservation,
    VideoReplay,
)
from src.streaming.streamer import Streamer
from src.talos_app import Tracker
from src.tracking.detector import DetectionBatch, Detector, SourceFrameMetadata
from src.tracking.yolo.results import local_detections_from_arrays


class StaticObservationModel:
    def detect_person(self, frame):
        assert np.all(frame == 4)
        return [LocalDetection((1, 2, 3, 4), 0.75, 6)]


def test_frame_packet_is_acquired_once_and_latest_reads_do_not_advance(
    monkeypatch, mocker
) -> None:
    frames = [
        np.full((2, 3, 3), 1, dtype=np.uint8),
        np.full((2, 3, 3), 2, dtype=np.uint8),
    ]
    fake_cap = mocker.Mock()
    fake_cap.read.side_effect = [(True, frame) for frame in frames]
    monkeypatch.setattr("src.connection.connection.cv2.VideoCapture", lambda _: fake_cap)

    timestamps = iter((10.0, 11.0))
    connection = VideoConnection(
        src=0, camera_id="camera-a", timestamp_provider=lambda: next(timestamps)
    )

    first = connection.get_latest_packet()
    assert first is connection.get_latest_packet()
    assert first is not None
    assert first.camera_id == "camera-a"
    assert first.frame_sequence == 0
    assert first.capture_timestamp == 10.0
    assert first.image.flags.writeable is False
    assert fake_cap.read.call_count == 1

    second = connection.capture_packet()
    assert second is connection.get_latest_packet()
    assert second is not None
    assert second.frame_sequence == 1
    assert second.capture_timestamp == 11.0
    assert fake_cap.read.call_count == 2


def test_streamer_reuses_latest_frame_without_advancing_source(mocker) -> None:
    image = np.zeros((2, 3, 3), dtype=np.uint8)
    video_connection = mocker.Mock()
    video_connection.get_latest_frame.return_value = image
    connection = SimpleNamespace(
        video_connection=video_connection, get_bboxes=lambda: []
    )
    streamer = Streamer({"camera-a": connection})

    assert streamer.get_frame("camera-a") is image
    assert streamer.get_frame("camera-a") is image
    assert video_connection.get_latest_frame.call_count == 2
    video_connection.get_frame.assert_not_called()


def test_streamer_draws_on_copy_without_mutating_shared_packet(mocker) -> None:
    image = np.zeros((100, 100, 3), dtype=np.uint8)
    image.setflags(write=False)
    video_connection = mocker.Mock()
    video_connection.get_latest_frame.return_value = image
    connection = SimpleNamespace(
        video_connection=video_connection,
        get_bboxes=lambda: [(10, 10, 30, 40)],
    )

    rendered = Streamer({"camera-a": connection}, draw_bboxes=True).get_frame(
        "camera-a"
    )

    assert rendered is not image
    assert np.count_nonzero(rendered) > 0
    assert np.count_nonzero(image) == 0


def test_prerecorded_video_replay_has_repeatable_sequence_and_timestamps() -> None:
    video_path = (
        Path(__file__).parents[2] / "video_sample" / "start_center_to_left.mp4"
    )

    def read_metadata() -> list[tuple[int, float]]:
        connection = VideoConnection(src=str(video_path), camera_id="camera-a")
        try:
            return [
                (packet.frame_sequence, packet.capture_timestamp)
                for packet in islice(VideoReplay(connection), 3)
            ]
        finally:
            connection.close()

    first_run = read_metadata()
    assert first_run == read_metadata()
    assert [sequence for sequence, _ in first_run] == [0, 1, 2]
    assert [timestamp for _, timestamp in first_run] == sorted(
        timestamp for _, timestamp in first_run
    )


def test_observation_jsonl_round_trip_preserves_empty_frames() -> None:
    output = StringIO()
    recorder = ObservationRecorder(output)
    observation = PersonObservation(
        camera_id="camera-a",
        frame_sequence=4,
        capture_timestamp=1.25,
        bounding_box=(10, 20, 30, 40),
        detection_confidence=0.875,
        local_track_id=7,
    )
    recorder.record(
        ObservationFrame("camera-a", 4, 1.25, observations=(observation,))
    )
    recorder.record(ObservationFrame("camera-a", 5, 1.5))

    serialized = output.getvalue()
    assert serialized.count("\n") == 2
    assert '"local_track_id":7' in serialized
    assert list(ObservationReplay(StringIO(serialized))) == [
        ObservationFrame("camera-a", 4, 1.25, observations=(observation,)),
        ObservationFrame("camera-a", 5, 1.5),
    ]


def test_saved_observations_replay_into_legacy_connection_view(mocker) -> None:
    output = StringIO()
    observation = PersonObservation(
        "camera-a", 0, 0.0, (1, 2, 3, 4), 0.9, 12
    )
    ObservationRecorder(output).record(
        ObservationFrame("camera-a", 0, 0.0, (observation,))
    )
    connection = SimpleNamespace(set_observations=mocker.Mock())

    frames = list(
        ObservationReplay(StringIO(output.getvalue())).replay_into(
            {"camera-a": connection}
        )
    )

    assert frames[0].observations == (observation,)
    connection.set_observations.assert_called_once_with([observation])


def test_detector_maps_metadata_and_preserves_legacy_bounding_boxes(mocker) -> None:
    first_connection = SimpleNamespace(set_observations=mocker.Mock())
    second_connection = SimpleNamespace(set_observations=mocker.Mock())
    recorder_output = StringIO()
    detector = Detector.__new__(Detector)
    detector.frame_order = [("first", 0), ("second", 100)]
    detector.connections = {
        "first": first_connection,
        "second": second_connection,
    }
    detector.waiting_startup = False
    detector._latest_observations = {}
    detector.observation_recorder = ObservationRecorder(recorder_output)
    detector._bbox_queue = Queue()
    detector._bbox_queue.put(
        DetectionBatch(
            sources=(
                SourceFrameMetadata("first", "camera-a", 8, 2.0, 0, 100),
                SourceFrameMetadata("second", "camera-b", 3, 2.1, 100, 100),
            ),
            detections=(
                LocalDetection((10, 20, 30, 40), 0.8, 5),
                LocalDetection((110, 25, 140, 50), 0.9, 9),
            ),
        )
    )

    legacy_bboxes = detector.get_bboxes()
    observations = detector.get_observations()

    assert legacy_bboxes == {
        "first": [(10, 20, 30, 40)],
        "second": [(10, 25, 40, 50)],
    }
    assert observations["first"][0].local_track_id == 5
    assert observations["first"][0].detection_confidence == 0.8
    assert observations["second"][0].camera_id == "camera-b"
    assert observations["second"][0].frame_sequence == 3
    first_connection.set_observations.assert_called_once_with(observations["first"])
    second_connection.set_observations.assert_called_once_with(observations["second"])
    assert len(list(ObservationReplay(StringIO(recorder_output.getvalue())))) == 2


def test_detector_worker_keeps_packet_metadata_with_model_output() -> None:
    shape = (2, 2, 3)
    memory = shared_memory.SharedMemory(create=True, size=np.zeros(shape, np.uint8).nbytes)
    try:
        shared_frame = np.ndarray(shape, dtype=np.uint8, buffer=memory.buf)
        shared_frame[:] = 4
        output_queue = Queue(maxsize=2)
        metadata_queue = Queue(maxsize=1)
        source = SourceFrameMetadata("host", "camera-a", 11, 3.5, 0, 2)
        metadata_queue.put((source,))
        stopper = threading.Event()
        frame_ready = threading.Event()
        frame_ready.set()
        worker = threading.Thread(
            target=Detector._detect_person_worker,
            args=(
                StaticObservationModel,
                output_queue,
                metadata_queue,
                stopper,
                frame_ready,
                memory,
                shape,
                np.uint8,
            ),
        )
        worker.start()

        batch = output_queue.get(timeout=2.0)
        stopper.set()
        worker.join(timeout=2.0)

        assert not worker.is_alive()
        assert batch == DetectionBatch(
            sources=(source,),
            detections=(LocalDetection((1, 2, 3, 4), 0.75, 6),),
        )
    finally:
        memory.close()
        memory.unlink()


def test_yolo_result_conversion_keeps_confidence_with_sorted_track_id() -> None:
    detections = local_detections_from_arrays(
        xyxy=np.array([[20.2, 21.8, 40.9, 50.1], [1.0, 2.0, 3.0, 4.0]]),
        confidences=np.array([0.6, 0.95]),
        track_ids=np.array([8, 3]),
    )

    assert detections == [
        LocalDetection((1, 2, 3, 4), 0.95, 3),
        LocalDetection((20, 21, 40, 50), 0.6, 8),
    ]


def test_tracker_acquires_each_source_once_and_detector_uses_same_batch(mocker) -> None:
    packets = {
        "first": FramePacket("camera-a", 1, 1.0, np.ones((2, 2, 3), np.uint8)),
        "second": FramePacket(
            "camera-b", 4, 1.1, np.full((2, 2, 3), 2, np.uint8)
        ),
    }
    video_connections = {}
    connections = {}
    for host in packets:
        video_connection = mocker.Mock()
        video_connection.capture_packet.return_value = packets[host]
        video_connections[host] = video_connection
        connections[host] = SimpleNamespace(video_connection=video_connection)

    tracker = Tracker.__new__(Tracker)
    tracker.connections = connections
    tracker._frame_batch_lock = threading.Lock()
    tracker._latest_frame_batch = {}
    captured_batch = tracker.capture_frames()

    for video_connection in video_connections.values():
        video_connection.capture_packet.assert_called_once_with()

    detector = Detector.__new__(Detector)
    detector.frame_order = [("first", 0), ("second", 2)]
    detector.connections = connections
    detector.waiting_startup = False
    detector._frame_ready_event = mocker.Mock()
    detector._frame_ready_event.is_set.return_value = False
    detector._frame_buf = np.zeros((2, 4, 3), dtype=np.uint8)
    detector._frame_metadata_queue = Queue(maxsize=1)
    detector._last_sent_sequences = {}

    detector.send_input(captured_batch)

    for video_connection in video_connections.values():
        video_connection.capture_packet.assert_called_once_with()
    assert np.all(detector._frame_buf[:, :2] == 1)
    assert np.all(detector._frame_buf[:, 2:] == 2)
    metadata = detector._frame_metadata_queue.get_nowait()
    assert [(item.camera_id, item.frame_sequence) for item in metadata] == [
        ("camera-a", 1),
        ("camera-b", 4),
    ]
    detector._frame_ready_event.set.assert_called_once_with()
