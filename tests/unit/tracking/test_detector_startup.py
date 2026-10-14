from types import SimpleNamespace

import pytest

from src.tracking.detector import DetectionWaitingForModel, Detector


class _FakeSMM:
    def start(self):
        pass

    def shutdown(self):
        pass

    def SharedMemory(self, size):  # noqa: N802 - mirrors SharedMemoryManager API
        raise AssertionError("shared memory must not be allocated without frames")


class _Connections(dict):
    def add_listener(self, _listener):
        pass

    def clear_bboxes(self):
        pass


def _conn(shape):
    return SimpleNamespace(video_connection=SimpleNamespace(shape=shape))


def _detector(connections, model=object):
    return Detector(model, connections, smm=_FakeSMM())


def test_start_defers_until_a_camera_has_produced_a_frame():
    detector = _detector(_Connections(cam=_conn(None)))

    detector.start()

    assert detector.is_pending_start() is True
    assert detector.is_running() is False


def test_send_input_waits_while_no_frame_and_starts_once_frames_arrive(mocker):
    connections = _Connections(cam=_conn(None))
    detector = _detector(connections)
    detector.start()
    start = mocker.patch.object(detector, "start")

    with pytest.raises(DetectionWaitingForModel):
        detector.send_input({})
    start.assert_not_called()

    connections["cam"].video_connection.shape = (4, 4, 3)
    with pytest.raises(DetectionWaitingForModel):
        detector.send_input({})
    start.assert_called_once_with()


def test_send_input_without_model_reports_waiting():
    detector = _detector(_Connections(cam=_conn((4, 4, 3))), model=None)

    with pytest.raises(DetectionWaitingForModel):
        detector.send_input({})


def test_clearing_model_cancels_pending_start():
    detector = _detector(_Connections(cam=_conn(None)))
    detector.start()

    detector.set_model(None)

    assert detector.is_pending_start() is False


def test_reset_frame_order_starts_pending_detector_when_frame_appears(mocker):
    connections = _Connections(cam=_conn(None))
    detector = _detector(connections)
    detector.start()
    start = mocker.patch.object(detector, "start")

    connections["cam"].video_connection.shape = (4, 4, 3)
    detector.reset_frame_order()

    start.assert_called_once_with()
