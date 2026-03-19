import socket

import pytest

from src.connection.operator_connections import OperatorConnection
from src.icd_config import CTypesInt, toBytes


class DummySocket(socket.socket):
    def __init__(self):
        self.sent = b""
        self.closed = False
        self.shutdown_called = False
        self.sockopt = 0

    def setsockopt(self, *_args, **_kwargs):
        pass

    def setblocking(self, *_args, **_kwargs):
        pass

    def connect(self, target):
        # Simulate successful connect
        self.connected_to = target

    def sendall(self, data: bytes):
        self.sent += data

    def shutdown(self, _how):
        self.shutdown_called = True

    def close(self):
        self.closed = True

    def getsockopt(self, *_args, **_kwargs):
        return self.sockopt

    def fileno(self):
        return 1


class DummyThread:
    def __init__(self, target=None, daemon=False):
        self.target = target
        self.join_called = False

    def start(self):
        if self.target:
            self.target()

    def join(self, timeout=None):
        self.join_called = True


@pytest.fixture(autouse=True)
def patch_thread(monkeypatch):
    """Patch threading.Thread so we can control thread behavior in tests."""

    import threading

    monkeypatch.setattr(threading, "Thread", DummyThread)
    yield


@pytest.fixture
def operator_connection(monkeypatch):
    """Create an OperatorConnection with a dummy socket."""

    dummy_socket = DummySocket()

    # Patch socket.socket so the instance uses our dummy socket
    monkeypatch.setattr(socket, "socket", lambda *args, **kwargs: dummy_socket)

    conn = OperatorConnection("localhost", 1234, connect_on_init=False)
    conn.socket = dummy_socket
    return conn


def test_xor_checksum_is_xor_of_all_bytes(operator_connection):
    data = b"\x01\x02\x03"
    assert operator_connection.xor_checksum(data) == 0x00  # 1^2^3 == 0


def test_publish_builds_expected_packet_and_increments_command_id(operator_connection):
    operator_connection.command_count = 0

    result = operator_connection.publish(command=1, payload=b"AB")

    assert result == 0
    assert operator_connection.command_count == 2

    expected_header = (
        toBytes(0, CTypesInt.UINT32)
        + toBytes(0, CTypesInt.UINT16)
        + toBytes(1, CTypesInt.UINT16)
        + toBytes(2, CTypesInt.UINT16)
    )
    expected_message = expected_header + b"AB"
    expected_crc = toBytes(operator_connection.xor_checksum(expected_message), CTypesInt.UINT8)

    assert operator_connection.socket.sent == expected_message + expected_crc


def test_publish_handles_socket_error(operator_connection, monkeypatch):
    class BadSocket(DummySocket):
        def sendall(self, _: bytes):
            raise OSError("fail")

    bad_socket = BadSocket()
    operator_connection.socket = bad_socket

    assert operator_connection.publish(command=1, payload=b"") == -1


def test_close_shuts_down_socket_and_joins_thread(operator_connection):
    dummy_thread = DummyThread()
    operator_connection.thread = dummy_thread

    operator_connection.close()

    assert operator_connection.is_running is False
    assert operator_connection.socket.shutdown_called
    assert dummy_thread.join_called
    assert operator_connection.socket.closed


def test_connect_calls_listen_on_success(monkeypatch, operator_connection):
    # Patch listen so it doesn't loop indefinitely
    called = {"listen": False}

    def fake_listen():
        called["listen"] = True

    operator_connection.listen = fake_listen

    operator_connection.connect()

    assert called["listen"] is True


def test_connect_retries_on_blockingio_then_succeeds(monkeypatch, operator_connection):
    # Simulate connect raising BlockingIOError first, then succeeding
    calls = {"count": 0}

    def connect_side_effect(target):
        if calls["count"] == 0:
            calls["count"] += 1
            raise BlockingIOError
        return None

    operator_connection.socket.connect = connect_side_effect

    # Make select.select report the socket as writeable, with no error
    monkeypatch.setattr(
        "select.select", lambda r, w, x, t: ([], [operator_connection.socket], [])
    )

    operator_connection.listen = lambda: None
    operator_connection.connect()

    assert calls["count"] == 1
