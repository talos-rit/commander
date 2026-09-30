import numpy as np
import pytest
from fastapi.testclient import TestClient

from src.interface.web.backend import CommanderWebBackend
from src.interface.web.server import create_web_app, encode_jpeg
from src.interface.web.state import WebOperatorState

from .fakes import FakeApp


@pytest.fixture
def setup(web_config):
    def build(camera_1="a", camera_2=None, static_dir=None, **state_kwargs):
        app = FakeApp(frame=np.full((20, 40, 3), 128, np.uint8))
        backend = CommanderWebBackend(
            app,
            WebOperatorState(camera_1=camera_1, camera_2=camera_2, **state_kwargs),
            persist_settings=lambda _updates: None,
            model_options=lambda: ["yolo_nano"],
        )
        backend.startup()
        return TestClient(create_web_app(backend, static_dir=static_dir)), app

    return build


def test_health_and_status_single_camera(setup):
    client, _ = setup()

    assert client.get("/api/health").json() == {"status": "ok", "ready": True}
    status = client.get("/api/status").json()
    assert status["view"]["available_slots"] == 1
    assert status["view"]["displayed_hosts"] == ["a"]
    assert status["connections"]["a"]["has_video"] is True


def test_api_refuses_calls_until_startup_finishes(web_config):
    app = FakeApp(frame=np.full((20, 40, 3), 128, np.uint8))
    persisted = []
    backend = CommanderWebBackend(
        app,
        WebOperatorState(camera_1="a"),
        persist_settings=persisted.append,
        model_options=lambda: ["yolo_nano"],
    )
    client = TestClient(create_web_app(backend, static_dir=None))

    assert client.get("/api/health").json() == {"status": "ok", "ready": False}
    for response in (
        client.get("/api/status"),
        client.put("/api/settings", json={"ui_mode": "debug"}),
        client.post("/api/view", json={"ui_mode": "debug"}),
    ):
        assert response.status_code == 503
        assert response.json()["starting"] is True
    assert persisted == []
    assert app.connections == {}

    backend.startup()

    assert client.get("/api/status").status_code == 200


def test_virtual_camera_toggle(setup):
    client, app = setup()

    started = client.post("/api/control/virtual-camera", json={"enabled": True})
    assert started.status_code == 200
    assert started.json() == {"enabled": True}
    assert client.get("/api/status").json()["virtual_camera"] is True
    assert ("start_stream", "pyvcam", None) in app.calls

    stopped = client.post("/api/control/virtual-camera", json={"enabled": False})
    assert stopped.json() == {"enabled": False}
    assert client.get("/api/status").json()["virtual_camera"] is False


def test_two_screen_rejected_with_single_camera(setup):
    client, _ = setup()

    response = client.post("/api/view", json={"display_mode": "two_screen"})

    assert response.status_code == 409
    assert "second camera" in response.json()["detail"]


def test_view_validation_rejects_unknown_values(setup):
    client, _ = setup()
    assert client.post("/api/view", json={"display_mode": "three"}).status_code == 422


def test_two_camera_view_select_and_home(setup):
    client, app = setup(camera_2="b")

    status = client.post("/api/view", json={"display_mode": "two_screen"}).json()
    assert status["view"]["displayed_hosts"] == ["a", "b"]
    status = client.post("/api/cameras/select", json={"host": "b"}).json()
    assert status["view"]["selected_host"] == "b"
    assert client.post("/api/control/home").json() == {"host": "b"}
    assert ("home", "b") in app.calls


def test_home_with_explicit_host(setup):
    client, app = setup(camera_2="b")
    assert client.post("/api/control/home", json={"host": "b"}).json() == {"host": "b"}


def test_auto_track_toggle(setup):
    client, app = setup()

    assert client.post("/api/control/auto-track", json={"enabled": True}).json() == {
        "enabled": True
    }
    assert app.connections["a"].is_manual is False


def test_slots_endpoint(setup):
    client, app = setup()

    status = client.post("/api/cameras/slots", json={"camera_1": "a", "camera_2": "b"}).json()

    assert status["view"]["available_slots"] == 2
    assert set(app.connections) == {"a", "b"}
    missing = client.post("/api/cameras/slots", json={"camera_1": "ghost"})
    assert missing.status_code == 404


def test_debug_controls_forbidden_in_simple_mode(setup):
    client, _ = setup()
    response = client.post("/api/control/move/start", json={"direction": "up"})
    assert response.status_code == 403


def test_debug_controls_in_debug_mode(setup):
    client, app = setup(ui_mode="debug")

    assert client.post("/api/control/move/start", json={"direction": "up"}).status_code == 200
    assert client.post("/api/control/move/stop", json={"direction": "up"}).status_code == 200
    assert client.post("/api/control/jog-mode", json={"mode": "continuous"}).json() == {
        "mode": "continuous"
    }
    assert client.post("/api/control/model", json={"model": "yolo_nano"}).json() == {
        "model": "yolo_nano"
    }
    assert client.post("/api/control/model", json={"model": "basic"}).status_code == 404
    assert ("start_move", "UP", "a") in app.calls
    assert client.post(
        "/api/control/joint/start", json={"axis": "shoulder", "direction": 1}
    ).status_code == 200
    assert client.post("/api/control/joint/stop").status_code == 200
    assert client.post(
        "/api/control/cartesian/start", json={"x": 0, "y": -1, "z": 0}
    ).status_code == 200
    assert client.post("/api/control/cartesian/stop").status_code == 200
    assert ("start_joint", 2, 1, "a") in app.calls
    assert ("start_cartesian", (0, -1, 0), "a") in app.calls


def test_command_without_camera_is_conflict(setup):
    client, _ = setup(camera_1=None)
    response = client.post("/api/control/home")
    assert response.status_code == 409


def test_snapshot_returns_jpeg(setup):
    client, _ = setup()

    response = client.get("/api/cameras/a/snapshot")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.content[:2] == b"\xff\xd8"


def test_snapshot_without_frame_is_unavailable(setup):
    client, _ = setup()
    assert client.get("/api/cameras/ghost/snapshot").status_code == 503


def test_mjpeg_streams_multipart_frames(setup):
    client, _ = setup()

    response = client.get("/api/cameras/a/mjpeg?frames=1&width=20")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("multipart/x-mixed-replace")
    assert response.content.startswith(b"--frame\r\nContent-Type: image/jpeg")
    assert b"\xff\xd8" in response.content
    assert response.content.endswith(b"\xff\xd9\r\n--frame\r\n")


def test_mjpeg_ends_when_server_is_stopping(setup):
    client, _ = setup()
    client.app.state.streams_stopping.set()

    response = client.get("/api/cameras/a/mjpeg")

    assert response.status_code == 200
    assert response.content == b"--frame\r\n"


def test_settings_roundtrip(setup):
    client, _ = setup()

    assert client.get("/api/settings").json()["ui_mode"] == "simple"
    updated = client.put("/api/settings", json={"ui_mode": "debug"}).json()
    assert updated["ui_mode"] in ("simple", "debug")
    assert client.get("/api/status").json()["view"]["ui_mode"] == "debug"
    bad = client.put("/api/settings", json={"web_port": 0})
    assert bad.status_code == 422


def test_robot_crud(setup):
    client, _ = setup()

    assert set(client.get("/api/robots").json()) == {"a", "b"}
    created = client.post(
        "/api/robots",
        json={"socket_host": "c", "socket_port": 5000, "camera_index": "rtsp://c"},
    )
    assert created.status_code == 201
    assert client.put("/api/robots/c", json={"fps": 10}).json()["fps"] == 10
    assert client.delete("/api/robots/c").status_code == 204
    assert client.delete("/api/robots/c").status_code == 404


def test_api_only_when_frontend_not_built(setup, tmp_path):
    client, _ = setup(static_dir=tmp_path / "missing")
    response = client.get("/")
    assert response.status_code == 503
    assert "pnpm" in response.json()["detail"]


def test_serves_built_spa_with_fallback(setup, tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>commander</html>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    (dist / "favicon.svg").write_text("<svg/>")
    client, _ = setup(static_dir=dist)

    assert "commander" in client.get("/").text
    assert "commander" in client.get("/settings").text
    assert client.get("/assets/app.js").text == "console.log(1)"
    assert client.get("/favicon.svg").text == "<svg/>"
    assert "commander" in client.get("/../secret").text


def test_encode_jpeg_downscales():
    frame = np.zeros((100, 200, 3), np.uint8)
    data = encode_jpeg(frame, max_width=50)
    assert data is not None and data[:2] == b"\xff\xd8"
    import cv2

    decoded = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    assert decoded.shape[:2] == (25, 50)
