import asyncio
import signal
import threading
from types import SimpleNamespace

import src.interface.web.runner as runner

from .fakes import FakeApp


def _patch_app(monkeypatch):
    created = {}

    def fake_app(_scheduler, smm=None, args=None):
        created["app"] = FakeApp()
        created["args"] = args
        return created["app"]

    monkeypatch.setattr(runner, "App", fake_app)
    monkeypatch.setattr(runner, "ThreadScheduler", lambda: object())
    monkeypatch.setattr(
        runner.multiprocessing.managers, "SharedMemoryManager", lambda: object()
    )
    monkeypatch.setattr(runner, "ensure_termination_guard", lambda: None)
    return created


def test_build_backend_uses_connection_arg_when_no_camera_configured(
    web_config, monkeypatch
):
    created = _patch_app(monkeypatch)

    backend = runner.build_backend(SimpleNamespace(connection="a"))
    assert backend.ready is False
    backend.startup()

    assert backend.ready is True
    assert backend.state.camera_1 == "a"
    assert "a" in created["app"].connections


def test_build_backend_prefers_saved_camera_slots(web_config, monkeypatch):
    _patch_app(monkeypatch)
    monkeypatch.setattr(runner.config.APP_SETTINGS, "camera_1_host", "b", raising=False)

    backend = runner.build_backend(SimpleNamespace(connection="a"))

    assert backend.state.camera_1 == "b"


def test_run_web_starts_uvicorn_on_configured_address(web_config, monkeypatch):
    _patch_app(monkeypatch)
    servers = []
    monkeypatch.setattr(runner._Server, "run", lambda self: servers.append(self))
    monkeypatch.setattr(runner, "web_dist_available", lambda: False)

    runner.run_web(None)

    config = servers[0].config
    assert config.host == "127.0.0.1"
    assert config.port == 8000
    assert config.timeout_graceful_shutdown == 2
    assert config.app.title == "Commander"


def test_ctrl_c_ends_mjpeg_streams_before_uvicorn_exits(web_config, monkeypatch):
    _patch_app(monkeypatch)
    servers = []
    monkeypatch.setattr(runner._Server, "run", lambda self: servers.append(self))
    runner.run_web(None)
    server = servers[0]
    stopping = server.config.app.state.streams_stopping

    server.handle_exit(signal.SIGINT, None)

    assert stopping.is_set()
    assert server.should_exit is True


def test_connections_open_only_after_the_server_is_listening(web_config, monkeypatch):
    _patch_app(monkeypatch)
    servers = []
    monkeypatch.setattr(runner._Server, "run", lambda self: servers.append(self))
    monkeypatch.setattr(runner, "web_dist_available", lambda: True)
    started = []
    monkeypatch.setattr(
        runner.CommanderWebBackend, "start_in_background", lambda self: started.append(self)
    )
    runner.run_web(None)
    server = servers[0]
    assert started == []

    async def fake_super_startup(self, sockets=None):
        self.started = True

    monkeypatch.setattr(runner.uvicorn.Server, "startup", fake_super_startup)
    asyncio.run(server.startup())

    assert len(started) == 1


def test_server_waits_for_startup_before_signal_cleanup(monkeypatch):
    order = []
    server = runner._Server(
        runner.uvicorn.Config(lambda *_: None),
        on_exit=lambda: None,
        before_cleanup=lambda: order.append("cancel"),
    )
    monkeypatch.setattr(signal, "raise_signal", lambda sig: order.append(("raise", sig)))
    server._captured_signals = [signal.SIGINT]

    with server.capture_signals():
        order.append("serving")

    assert order == ["serving", "cancel", ("raise", signal.SIGINT)]


def test_cancel_startup_stops_before_the_next_host(web_config, monkeypatch):
    created = _patch_app(monkeypatch)
    monkeypatch.setattr(runner.config.APP_SETTINGS, "camera_1_host", "a", raising=False)
    monkeypatch.setattr(runner.config.APP_SETTINGS, "camera_2_host", "b", raising=False)
    backend = runner.build_backend(None)
    app = created["app"]
    opening = threading.Event()
    release = threading.Event()
    original_open = app.open_connection

    def slow_open(host):
        opening.set()
        release.wait(2)
        original_open(host)

    monkeypatch.setattr(app, "open_connection", slow_open)

    thread = backend.start_in_background()
    assert opening.wait(2)
    canceller = threading.Thread(target=backend.cancel_startup)
    canceller.start()
    release.set()
    canceller.join(2)
    thread.join(2)

    assert list(app.connections) == ["a"]
    assert backend.ready is True
