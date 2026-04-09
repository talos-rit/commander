import importlib
import sys
import types

import pytest
from fastapi.testclient import TestClient


# talos_endpoint imports src.talos_app at module import time, which can pull in
# heavy dependencies and trigger circular imports during isolated unit tests.
fake_talos_app_module = types.ModuleType("src.talos_app")
fake_talos_app_module.App = object
sys.modules["src.talos_app"] = fake_talos_app_module
talos_endpoint = importlib.import_module("src.talos_endpoint")


class DummyConnection:
    def __init__(self, host):
        self.host = host


class DummyConnections(dict):
    def __init__(self, active=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._active = active

    def get_active(self):
        return self._active


class DummyTalosApp:
    def __init__(self, active_hostname=None, is_streaming=False, active_conn=None):
        self._active_hostname = active_hostname
        self._is_streaming = is_streaming
        self.connections = DummyConnections(active=active_conn)
        self.start_stream_calls = []
        self.stop_stream_calls = 0

    def get_active_hostname(self):
        return self._active_hostname

    def is_streaming(self):
        return self._is_streaming

    def start_stream(self, streamer_type, hostname, stream_config):
        self.start_stream_calls.append(
            {
                "streamer_type": streamer_type,
                "hostname": hostname,
                "stream_config": stream_config,
            }
        )
        self._is_streaming = True

    def stop_stream(self):
        self.stop_stream_calls += 1
        self._is_streaming = False


@pytest.fixture(autouse=True)
def reset_global_app_instance(monkeypatch):
    monkeypatch.setattr(talos_endpoint, "_talos_app_instance", None)


def test_health_returns_uninitialized_when_app_missing():
    with TestClient(talos_endpoint.app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "uninitialized"}


def test_health_returns_ok_when_initialized(monkeypatch):
    monkeypatch.setattr(talos_endpoint, "_talos_app_instance", DummyTalosApp())

    with TestClient(talos_endpoint.app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root_returns_503_without_active_connection(monkeypatch):
    monkeypatch.setattr(
        talos_endpoint,
        "_talos_app_instance",
        DummyTalosApp(active_hostname=None, is_streaming=False, active_conn=None),
    )

    with TestClient(talos_endpoint.app) as client:
        response = client.get("/")

    assert response.status_code == 503
    assert "No active camera connection" in response.json()["detail"]


def test_root_redirects_when_stream_running(monkeypatch):
    app = DummyTalosApp(
        active_hostname="robot.local",
        is_streaming=False,
        active_conn=DummyConnection("robot.local"),
    )
    monkeypatch.setattr(talos_endpoint, "_talos_app_instance", app)

    with TestClient(talos_endpoint.app) as client:
        response = client.get("/", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"].endswith("/stream/")
    assert len(app.start_stream_calls) == 1


def test_root_returns_503_when_stream_fails_to_start(monkeypatch):
    class NonStartingTalosApp(DummyTalosApp):
        def start_stream(self, streamer_type, hostname, stream_config):
            self.start_stream_calls.append(
                {
                    "streamer_type": streamer_type,
                    "hostname": hostname,
                    "stream_config": stream_config,
                }
            )

    app = NonStartingTalosApp(
        active_hostname="robot.local",
        is_streaming=False,
        active_conn=DummyConnection("robot.local"),
    )
    monkeypatch.setattr(talos_endpoint, "_talos_app_instance", app)

    with TestClient(talos_endpoint.app) as client:
        response = client.get("/")

    assert response.status_code == 503
    assert "Failed to start stream" in response.json()["detail"]


def test_status_endpoint_reports_connection_state(monkeypatch):
    active_conn = DummyConnection("robot.local")
    app = DummyTalosApp(
        active_hostname="robot.local",
        is_streaming=True,
        active_conn=active_conn,
    )
    app.connections["robot.local"] = active_conn
    monkeypatch.setattr(talos_endpoint, "_talos_app_instance", app)

    with TestClient(talos_endpoint.app) as client:
        response = client.get("/status")

    assert response.status_code == 200
    data = response.json()
    assert data["active_hostname"] == "robot.local"
    assert data["connections"] == ["robot.local"]
    assert data["is_streaming"] is True
    assert data["tracker_active_connection"] == "robot.local"


def test_stream_start_rejects_missing_output_url(monkeypatch):
    monkeypatch.setattr(talos_endpoint, "_talos_app_instance", DummyTalosApp())

    with TestClient(talos_endpoint.app) as client:
        response = client.post("/stream/start", json={})

    assert response.status_code == 400
    assert response.json()["detail"] == "Missing output_url"


def test_stream_start_calls_talos_app(monkeypatch):
    app = DummyTalosApp()
    monkeypatch.setattr(talos_endpoint, "_talos_app_instance", app)

    payload = {
        "output_url": "rtsp://localhost:8554/custom",
        "hostname": "robot.local",
        "fps": 25,
        "use_docker": True,
        "docker_image": "img",
        "docker_network": "net",
    }

    with TestClient(talos_endpoint.app) as client:
        response = client.post("/stream/start", json=payload)

    assert response.status_code == 200
    assert response.json() == {
        "status": "started",
        "output_url": "rtsp://localhost:8554/custom",
    }
    assert len(app.start_stream_calls) == 1
    call = app.start_stream_calls[0]
    assert call["streamer_type"] == "ffmpeg"
    assert call["hostname"] == "robot.local"
    assert call["stream_config"]["output_url"] == "rtsp://localhost:8554/custom"
    assert call["stream_config"]["fps"] == 25
    assert call["stream_config"]["use_docker"] is True


def test_stream_stop_calls_talos_app_stop(monkeypatch):
    app = DummyTalosApp()
    monkeypatch.setattr(talos_endpoint, "_talos_app_instance", app)

    with TestClient(talos_endpoint.app) as client:
        response = client.post("/stream/stop")

    assert response.status_code == 200
    assert response.json() == {"status": "stopped"}
    assert app.stop_stream_calls >= 1


def test_lifespan_shutdown_stops_stream(monkeypatch):
    app = DummyTalosApp(active_hostname="robot.local", is_streaming=True)
    monkeypatch.setattr(talos_endpoint, "_talos_app_instance", app)

    with TestClient(talos_endpoint.app):
        pass

    assert app.stop_stream_calls == 1
