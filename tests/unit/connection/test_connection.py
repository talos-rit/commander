import time

import numpy as np
import pytest

import src.connection.connection as connection_module


class DummyVideoFrame:
    def __init__(self, pts=0, time_base=1.0):
        self.pts = pts
        self.time_base = time_base
        self.shape = (10, 10, 3)
        self.dtype = np.dtype("uint8")

    def to_ndarray(self, format=None):
        return np.zeros(self.shape, dtype=self.dtype)


def test_pyavcapture_read_returns_frame_and_time(monkeypatch, mocker):
    frame = DummyVideoFrame(pts=10, time_base=0.5)

    packet = mocker.Mock()
    packet.decode.return_value = [frame]

    container = mocker.Mock()
    container.streams = [mocker.Mock(type="video", time_base=0.5)]
    container.demux.return_value = [packet]
    container.start_time = 2.0
    container.closed = False
    container.close.side_effect = lambda: setattr(container, "closed", True)

    monkeypatch.setattr(connection_module.av, "open", lambda source, options=None: container)
    monkeypatch.setattr(connection_module.av.video.frame, "VideoFrame", DummyVideoFrame)

    term_ids = []
    monkeypatch.setattr(connection_module, "add_termination_handler", lambda f: term_ids.append(123) or 123)
    monkeypatch.setattr(connection_module, "remove_termination_handler", lambda term: term_ids.append(f"removed-{term}"))

    cap = connection_module.PyAVCapture("rtsp://fake")

    now = time.time()
    monkeypatch.setattr(time, "time", lambda: now)
    ok, img, abs_time = cap.read()

    assert ok is True
    assert isinstance(img, np.ndarray)
    assert abs_time == pytest.approx(
        now - (container.start_time / connection_module.av.time_base) + frame.pts * frame.time_base
    )

    ok2, img2, abs2 = cap.read()
    assert ok2 is False and img2 is None and abs2 is None
    assert cap.more is False

    cap.release()
    assert container.closed is True
    assert term_ids == [123, "removed-123"]


def test_video_connection_initializes_with_cv2_and_sets_shape(monkeypatch, mocker):
    fake_cap = mocker.Mock()
    fake_cap.read.side_effect = [
        (True, np.zeros((5, 5, 3), dtype=np.uint8)),
        (False, None),
    ]
    fake_cap.release = mocker.Mock()

    monkeypatch.setattr(connection_module.cv2, "VideoCapture", lambda source: fake_cap)
    monkeypatch.setattr(connection_module.cv2, "CAP_PROP_BUFFERSIZE", 123)

    vc = connection_module.VideoConnection(src="0", video_buffer_size=5)
    assert vc.shape == (5, 5, 3)
    assert vc.dtype == np.dtype("uint8")

    assert vc.get_frame() is None

    vc.close()
    fake_cap.release.assert_called_once()


def test_video_connection_initializes_with_pyav(monkeypatch, mocker, no_termination_handlers):
    frame = DummyVideoFrame(pts=10, time_base=0.5)
    packet = mocker.Mock()
    packet.decode.return_value = [frame]

    container = mocker.Mock()
    container.streams = [mocker.Mock(type="video", time_base=0.5)]
    container.demux.return_value = [packet]
    container.start_time = 2.0
    container.closed = False
    container.close.side_effect = lambda: setattr(container, "closed", True)

    monkeypatch.setattr(connection_module.av, "open", lambda source, options=None: container)
    monkeypatch.setattr(connection_module.av.video.frame, "VideoFrame", DummyVideoFrame)

    no_termination_handlers(connection_module)

    vc = connection_module.VideoConnection(src="rtsp://fake")
    assert vc.shape == frame.shape
    assert vc.dtype == frame.dtype

    vc.close()
    assert container.closed is True


def test_video_connection_falls_back_when_no_frame(monkeypatch, mocker):
    fake_cap = mocker.Mock()
    fake_cap.read.return_value = (False, None)
    fake_cap.release = mocker.Mock()

    monkeypatch.setattr(connection_module.cv2, "VideoCapture", lambda source: fake_cap)
    monkeypatch.setattr(connection_module.cv2, "CAP_PROP_BUFFERSIZE", 1)

    vc = connection_module.VideoConnection(src="0")
    assert vc.shape is None


def test_connection_set_and_toggle_manual(monkeypatch, mocker):
    # Publisher is only instantiated; using a simple mock avoids needing behavior.
    mock_pub = mocker.Mock(spec=connection_module.Publisher)
    monkeypatch.setattr(connection_module, "Publisher", mocker.Mock(return_value=mock_pub))

    monkeypatch.setitem(connection_module.ROBOT_CONFIGS, "host", type("C", (), {"manual_only": True})())

    conn = connection_module.Connection(host="host", port=1, video_connection=None)
    assert conn.is_manual is True
    conn.set_manual(False)
    assert conn.is_manual is False
    assert conn.toggle_manual() is True


def test_connection_close_invokes_subcomponents(monkeypatch, mocker):
    mock_pub = mocker.Mock(spec=connection_module.Publisher)
    monkeypatch.setattr(connection_module, "Publisher", mocker.Mock(return_value=mock_pub))

    monkeypatch.setitem(connection_module.ROBOT_CONFIGS, "host", type("C", (), {"manual_only": False})())

    vid_conn = mocker.Mock(spec=connection_module.VideoConnection)
    conn = connection_module.Connection(host="host", port=1, video_connection=vid_conn)
    conn.close()

    vid_conn.close.assert_called_once()
    mock_pub.close.assert_called_once()


def test_connection_collection_listener_notification(mocker, no_termination_handlers):
    events = []

    def listener(event, hostname, connection):
        events.append((event, hostname, connection))

    no_termination_handlers(connection_module)

    conn_mock = mocker.Mock(spec=connection_module.Connection)

    coll = connection_module.ConnectionCollection()
    coll.add_listener(listener)

    coll["h1"] = conn_mock
    assert events[0][0] == connection_module.ConnectionCollectionEvent.ADDED
    assert events[1][0] == connection_module.ConnectionCollectionEvent.ACTIVE_CHANGED

    coll.set_active(None)
    assert events[-1][0] == connection_module.ConnectionCollectionEvent.ACTIVE_CHANGED

def test_connection_collection_del_item(mocker, no_termination_handlers):
    closed = {}

    def fake_close():
        closed["called"] = True

    no_termination_handlers(connection_module)

    conn_mock = mocker.Mock(spec=connection_module.Connection)
    conn_mock.close.side_effect = fake_close

    coll = connection_module.ConnectionCollection()
    coll["h1"] = conn_mock
    del coll["h1"]

    assert closed.get("called") is True

def test_connection_collection_pop_item(mocker, no_termination_handlers):
    closed = {}

    def fake_close():
        closed["called"] = True

    no_termination_handlers(connection_module)

    conn_mock = mocker.Mock(spec=connection_module.Connection)
    conn_mock.close.side_effect = fake_close

    coll = connection_module.ConnectionCollection()
    coll["h1"] = conn_mock
    popped = coll.pop("h1")

    assert popped == conn_mock
    assert closed.get("called") is True

def test_connection_collection_set_active_nonexistent_logs(monkeypatch):
    coll = connection_module.ConnectionCollection()

    errors = []

    def fake_error(msg):
        errors.append(msg)

    monkeypatch.setattr(connection_module.logger, "error", fake_error)

    assert coll.set_active("missing") is None
    assert any("does not exist" in m for m in errors)


def test_connection_collection_clear_calls_remove_termination_handler(monkeypatch, mocker):
    called = {}

    def fake_add(f):
        called["term"] = True
        return 999

    def fake_remove(term):
        called["removed"] = term

    monkeypatch.setattr(connection_module, "add_termination_handler", fake_add)
    monkeypatch.setattr(connection_module, "remove_termination_handler", fake_remove)

    conn_mock = mocker.Mock(spec=connection_module.Connection)

    coll = connection_module.ConnectionCollection()
    coll["h1"] = conn_mock

    coll.clear()

    assert called.get("term") is True
    assert called.get("removed") == 999
    conn_mock.close.assert_called_once()
