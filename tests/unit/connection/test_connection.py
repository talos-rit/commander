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

    monkeypatch.setattr(connection_module.av, "open", lambda source, options=None, **_: container)
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

    monkeypatch.setattr(connection_module.av, "open", lambda source, options=None, **_: container)
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


def test_is_live_source_distinguishes_files(tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"")
    assert connection_module.is_live_source(0) is True
    assert connection_module.is_live_source("1") is True
    assert connection_module.is_live_source("rtsp://cam/stream") is True
    assert connection_module.is_live_source(str(video)) is False


class _StreamingCap:
    """Fake live camera that yields an increasing value on every read."""

    def __init__(self):
        self.reads = 0
        self.released = False

    def set(self, *_):
        return True

    def read(self):
        if self.released:
            return False, None
        self.reads += 1
        time.sleep(0.002)
        return True, np.full((4, 4, 3), self.reads % 255, dtype=np.uint8)

    def release(self):
        self.released = True


def test_background_capture_drains_and_capture_packet_does_not_advance(
    monkeypatch, no_termination_handlers
):
    cap = _StreamingCap()
    monkeypatch.setattr(connection_module.cv2, "VideoCapture", lambda source: cap)
    no_termination_handlers(connection_module)

    vc = connection_module.VideoConnection(src="0", background_capture=True)
    try:
        assert vc.shape == (4, 4, 3)
        time.sleep(0.05)
        packet = vc.capture_packet()
        assert packet is not None
        reads_before = cap.reads
        time.sleep(0.05)
        assert cap.reads > reads_before, "drain thread should keep reading"
        assert vc.get_latest_packet().frame_sequence > packet.frame_sequence
    finally:
        vc.close()
    assert cap.released is True
    assert vc._thread is None


def test_background_capture_reconnects_after_stream_loss(
    monkeypatch, no_termination_handlers
):
    caps = []

    class _DyingCap(_StreamingCap):
        def read(self):
            if self.reads >= 2:
                return False, None
            return super().read()

    def factory(_source):
        cap = _DyingCap() if not caps else _StreamingCap()
        caps.append(cap)
        return cap

    monkeypatch.setattr(connection_module.cv2, "VideoCapture", factory)
    no_termination_handlers(connection_module)

    vc = connection_module.VideoConnection(
        src="0", background_capture=True, reconnect_delay=0.01
    )
    try:
        deadline = time.monotonic() + 2.0
        while len(caps) < 2 and time.monotonic() < deadline:
            time.sleep(0.01)
        assert len(caps) >= 2
        assert caps[0].released is True
    finally:
        vc.close()


def test_background_close_never_releases_during_a_read(
    monkeypatch, no_termination_handlers
):
    class _GuardedCap(_StreamingCap):
        def __init__(self):
            super().__init__()
            self.in_read = False
            self.released_mid_read = False

        def read(self):
            self.in_read = True
            try:
                time.sleep(0.01)
                return super().read()
            finally:
                self.in_read = False

        def release(self):
            self.released_mid_read = self.in_read
            super().release()

    cap = _GuardedCap()
    monkeypatch.setattr(connection_module.cv2, "VideoCapture", lambda source: cap)
    no_termination_handlers(connection_module)

    vc = connection_module.VideoConnection(src="0", background_capture=True)
    time.sleep(0.03)
    vc.close()

    assert cap.released is True
    assert cap.released_mid_read is False
    assert vc._thread is None


def test_connection_initializes_manual_flags(monkeypatch, mocker):
    # Publisher is only instantiated; using a simple mock avoids needing behavior.
    mock_pub = mocker.Mock(spec=connection_module.Publisher)
    monkeypatch.setattr(connection_module, "Publisher", mocker.Mock(return_value=mock_pub))

    monkeypatch.setitem(connection_module.config.ROBOT_CONFIGS, "host", type("C", (), {"manual_only": True})())

    conn = connection_module.Connection(host="host", port=1, video_connection=None)
    assert conn.is_manual is True
    assert conn.is_manual_only is True


def test_connection_close_invokes_subcomponents(monkeypatch, mocker):
    mock_pub = mocker.Mock(spec=connection_module.Publisher)
    monkeypatch.setattr(connection_module, "Publisher", mocker.Mock(return_value=mock_pub))

    monkeypatch.setitem(connection_module.config.ROBOT_CONFIGS, "host", type("C", (), {"manual_only": False})())

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
