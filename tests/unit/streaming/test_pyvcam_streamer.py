import threading

import numpy as np
import pytest

from src.streaming.pyvcam_streamer import PyVcamStreamConfig, PyVcamStreamController


@pytest.fixture()
def sample_frame() -> np.ndarray:
    """A small sample frame used to validate dimensions and send behavior."""
    return np.zeros((2, 3, 3), dtype=np.uint8)


@pytest.fixture()
def one_frame_getter(sample_frame: np.ndarray):
    """Return a frame once, then None forever."""

    called = {"count": 0}

    def getter():
        if called["count"] == 0:
            called["count"] += 1
            return sample_frame
        return None

    return getter


def test_wait_for_frame_returns_first_frame(one_frame_getter, sample_frame):

    controller = PyVcamStreamController(frame_getter=one_frame_getter, config=PyVcamStreamConfig())

    result = controller._wait_for_frame(timeout_s=1.0)

    assert result is sample_frame


def test_wait_for_frame_times_out(monkeypatch):

    controller = PyVcamStreamController(frame_getter=lambda: None, config=PyVcamStreamConfig())

    # Make time.monotonic advance so that it always reports timeout
    times = [0.0, 0.01, 0.02, 0.03]

    def fake_monotonic():
        return times.pop(0) if times else 100.0

    monkeypatch.setattr("src.streaming.pyvcam_streamer.time.monotonic", fake_monotonic)
    monkeypatch.setattr("src.streaming.pyvcam_streamer.time.sleep", lambda _: None)

    with pytest.raises(RuntimeError, match="Timed out waiting for a video frame"):
        controller._wait_for_frame(timeout_s=0.001)


def test_start_registers_termination_handler_and_starts_thread(mocker, one_frame_getter):

    term_id = 999

    mock_add = mocker.patch(
        "src.streaming.pyvcam_streamer.add_termination_handler", return_value=term_id
    )

    mock_thread = mocker.Mock(spec=threading.Thread)
    mock_thread.is_alive.return_value = True

    mock_thread_cls = mocker.patch(
        "src.streaming.pyvcam_streamer.threading.Thread", return_value=mock_thread
    )
    mock_camera = mocker.patch("src.streaming.pyvcam_streamer.pyvcam.Camera")

    config = PyVcamStreamConfig(fps=12)
    controller = PyVcamStreamController(frame_getter=one_frame_getter, config=config)

    controller.start()

    assert controller._is_running is True
    assert controller._term_id == term_id
    mock_add.assert_called_once_with(controller.stop)
    mock_camera.assert_called_once_with(width=3, height=2, fps=12, fmt=mocker.ANY)
    mock_thread.start.assert_called_once()
    mock_thread_cls.assert_called_once_with(
        target=controller._stream_loop,
        name="pyvcam-stream",
        daemon=True,
    )


def test_stop_joins_thread_and_removes_termination_handler(mocker):

    mock_remove = mocker.patch("src.streaming.pyvcam_streamer.remove_termination_handler")

    controller = PyVcamStreamController(frame_getter=lambda: None, config=PyVcamStreamConfig())
    mock_thread = mocker.Mock(spec=threading.Thread)
    camera = mocker.Mock()
    controller._thread = mock_thread
    controller._term_id = 42
    controller._camera = camera

    controller.stop(timeout_s=0.5)

    mock_thread.join.assert_called_once_with(timeout=0.5)
    camera.close.assert_called_once()
    mock_remove.assert_called_once_with(42)
    assert controller._term_id is None
    assert controller._camera is None


def test_start_closes_nothing_and_drops_handler_when_camera_fails(mocker, one_frame_getter):
    mock_remove = mocker.patch("src.streaming.pyvcam_streamer.remove_termination_handler")
    mocker.patch("src.streaming.pyvcam_streamer.add_termination_handler", return_value=7)
    mocker.patch(
        "src.streaming.pyvcam_streamer.pyvcam.Camera",
        side_effect=RuntimeError("obs backend: virtual camera is not installed"),
    )
    mock_thread = mocker.patch("src.streaming.pyvcam_streamer.threading.Thread")

    controller = PyVcamStreamController(frame_getter=one_frame_getter, config=PyVcamStreamConfig())

    with pytest.raises(RuntimeError, match="virtual camera is not installed"):
        controller.start()

    mock_thread.assert_not_called()
    mock_remove.assert_called_once_with(7)
    assert controller._term_id is None
    assert controller.is_running() is False


def test_stream_loop_sends_frame_and_exits(mocker, sample_frame):

    mock_cam = mocker.Mock()
    mock_cam.width = 3
    mock_cam.height = 2
    stop_event = threading.Event()

    def frame_getter():
        if not stop_event.is_set():
            stop_event.set()
            return sample_frame
        return None

    controller = PyVcamStreamController(frame_getter=frame_getter, config=PyVcamStreamConfig())
    controller._stop_event = stop_event
    controller._camera = mock_cam

    controller._stream_loop()

    mock_cam.send.assert_called_once_with(sample_frame)
    mock_cam.sleep_until_next_frame.assert_called_once()


def test_is_running_depends_on_thread_state(mocker):
    controller = PyVcamStreamController(frame_getter=lambda: None, config=PyVcamStreamConfig())

    controller._thread = None
    assert controller.is_running() is False

    mock_thread = mocker.Mock(spec=threading.Thread)
    mock_thread.is_alive.return_value = True
    controller._thread = mock_thread
    assert controller.is_running() is True
