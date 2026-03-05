"""
This file contains integration tests for the OperatorConnection class, which
manages a TCP connection to an operator interface. The tests verify that the
connection can be established, messages can be received, and that the
connection properly handles shutdown and peer disconnection scenarios.
"""

import socket
import threading
import time

import pytest

import src.connection.operator_connections as operator_connections_module
from src.connection.operator_connections import OperatorConnection


def wait_until(predicate, timeout=2.0, interval=0.01):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


@pytest.fixture
def no_termination_handlers(monkeypatch):
    monkeypatch.setattr(
        operator_connections_module, "add_termination_handler", lambda _call: None
    )
    monkeypatch.setattr(
        operator_connections_module,
        "remove_termination_handler",
        lambda _handler_id: None,
    )


@pytest.fixture
def tcp_server():
    resources = {
        "connected": threading.Event(),
        "client": None,
        "server": None,
        "thread": None,
    }

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    resources["server"] = server

    def start(handler):
        def run():
            try:
                client, _ = server.accept()
                resources["client"] = client
                resources["connected"].set()
                handler(client)
            except OSError:
                pass

        thread = threading.Thread(target=run, daemon=True)
        resources["thread"] = thread
        thread.start()

    yield server.getsockname(), start, resources

    client = resources["client"]
    if client is not None:
        try:
            client.close()
        except OSError:
            pass

    try:
        server.close()
    except OSError:
        pass

    thread = resources["thread"]
    if thread is not None:
        thread.join(timeout=1.0)


class RecordingOperatorConnection(OperatorConnection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.messages = []
        self.received_event = threading.Event()

    def _on_message(self, message: bytes):
        self.messages.append(message)
        self.received_event.set()


def test_connects_to_socket(tcp_server):
    (host, port), start_server, resources = tcp_server

    def handler(client):
        while True:
            try:
                data = client.recv(1024)
            except OSError:
                break
            if not data:
                break

    start_server(handler)

    connection = OperatorConnection(host, port, connect_on_init=False)
    connection.connect_on_thread()

    assert resources["connected"].wait(timeout=2.0)
    assert connection.thread is not None
    assert connection.thread.is_alive()

    connection.close()


def test_receives_messages(tcp_server):
    (host, port), start_server, _ = tcp_server

    def handler(client):
        client.sendall(b"hello-from-server")
        time.sleep(0.2)

    start_server(handler)

    connection = RecordingOperatorConnection(host, port, connect_on_init=False)
    connection.connect_on_thread()

    assert connection.received_event.wait(timeout=2.0)
    assert any(message == b"hello-from-server" for message in connection.messages)

    connection.close()


def test_shutdown_closes_socket_and_thread(tcp_server):
    (host, port), start_server, resources = tcp_server

    def handler(client):
        while True:
            try:
                data = client.recv(1024)
            except OSError:
                break
            if not data:
                break

    start_server(handler)

    connection = OperatorConnection(host, port, connect_on_init=False)
    connection.connect_on_thread()

    assert resources["connected"].wait(timeout=2.0)

    connection.close()

    assert connection.is_running is False
    assert connection.socket.fileno() == -1
    assert connection.thread is not None
    assert not connection.thread.is_alive()


def test_handles_peer_closing_connection(tcp_server):
    (host, port), start_server, resources = tcp_server

    def handler(client):
        time.sleep(0.1)
        client.close()

    start_server(handler)

    connection = OperatorConnection(host, port, connect_on_init=False)
    connection.connect_on_thread()

    assert resources["connected"].wait(timeout=2.0)
    assert wait_until(
        lambda: connection.thread is not None and not connection.thread.is_alive(),
        timeout=2.0,
    )

    connection.close()
