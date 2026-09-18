import numpy as np
import pytest

from src.tracking.detector import DetectionWaitingForModel, Detector


class DummyModel:
    pass


def _connection(shape=None, frame=None):
    video = type("Video", (), {})()
    video.shape = shape
    video.get_frame = lambda: frame
    conn = type("Conn", (), {})()
    conn.video_connection = video
    conn.get_bboxes = lambda: None
    conn.set_bboxes = lambda bboxes: None
    return conn


def _connections(items: dict, mocker):
    connections = mocker.MagicMock()
    connections.items.return_value = list(items.items())
    connections.__iter__.side_effect = lambda: iter(items)
    connections.__len__.side_effect = lambda: len(items)
    connections.__getitem__.side_effect = items.__getitem__
    connections.add_listener = lambda listener: None
    connections.clear_bboxes = lambda: None
    return connections


def _detector(mocker, items: dict) -> Detector:
    smm = mocker.Mock()
    detector = Detector(
        DummyModel, _connections(items, mocker), smm=smm
    )
    return detector


def test_create_frame_order_skips_cameras_without_shape():
    missing = _connection(shape=None)
    ready = _connection(shape=(480, 640, 3))
    connections = {"late": missing, "ready": ready}

    assert Detector._create_frame_order(connections) == [("ready", 0)]

    missing.video_connection.shape = (480, 640, 3)
    assert Detector._create_frame_order(connections) == [
        ("late", 0),
        ("ready", 640),
    ]


def test_start_defers_until_a_frame_shape_exists(mocker):
    detector = _detector(mocker, {"bluey.local": _connection(shape=None)})

    detector.start()

    assert detector._pending_start is True
    assert detector.is_running() is False
    detector._smm.SharedMemory.assert_not_called()


def test_send_input_starts_once_shape_appears(mocker):
    conn = _connection(shape=None)
    detector = _detector(mocker, {"bluey.local": conn})
    detector._pending_start = True
    detector.start = mocker.Mock()

    with pytest.raises(DetectionWaitingForModel, match="live camera frame"):
        detector.send_input()
    detector.start.assert_not_called()

    conn.video_connection.shape = (480, 640, 3)
    detector.send_input()
    detector.start.assert_called_once()


def test_send_input_copies_latest_frame_when_running(mocker):
    frame = np.zeros((4, 4, 3), dtype=np.uint8)
    conn = _connection(shape=frame.shape, frame=frame)
    detector = _detector(mocker, {"bluey.local": conn})
    detector._pending_start = False
    detector._allocated_shape = frame.shape
    detector._frame_buf = np.ones(frame.shape, dtype=np.uint8)
    detector._frame_ready_event = mocker.Mock()
    detector._frame_ready_event.is_set.return_value = False
    detector.is_running = lambda: True

    detector.send_input()

    assert np.array_equal(detector._frame_buf, frame)
    detector._frame_ready_event.set.assert_called_once()
