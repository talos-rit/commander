import pytest
import cv2
import numpy as np
from types import SimpleNamespace
from fastapi.testclient import TestClient

import src.config as config
from src.interface.web.backend import BackendError
from src.interface.web.server import create_web_app
from src.tracking.pi_vision import PiVisionControl

from .fakes import robot
from .test_backend import make_backend


class Control:
    def __init__(self):
        self.enabled = False
        self.closed = False
        self.handoffs = 0

    def set_enabled(self, enabled):
        self.enabled = enabled
        return enabled

    def manual_handoff(self):
        self.handoffs += 1

    def status(self):
        return {"enabled": self.enabled, "subjects": 2}

    def close(self):
        self.enabled = False
        self.closed = True


def test_pi_auto_track_uses_existing_connection_without_loading_local_model(web_config):
    backend, app, _ = make_backend(camera_1="a", ui_mode="debug")
    backend.startup()
    control = Control()
    backend._pi_vision["a"] = control
    assert backend.set_auto_track(True)
    assert app.connections["a"].is_manual
    assert app.model is None
    assert control.handoffs == 1
    assert backend.status()["connections"]["a"]["auto_tracking"]
    backend.move("right", True)
    assert not control.enabled


def test_clear_error_dispatches_con_to_selected_robot_and_releases_tracking(web_config):
    backend, app, _ = make_backend(camera_1="a", camera_2="b")
    backend.startup()
    control = Control()
    control.enabled = True
    backend._pi_vision["a"] = control
    calls = []
    app.connections["a"].publisher.erv_enable_control = lambda: calls.append("CON")
    client = TestClient(create_web_app(backend))
    response = client.post("/api/control/clear-error", json={})
    assert response.status_code == 200
    assert response.json() == {"host": "a"}
    assert calls == ["CON"]
    assert not control.enabled


def test_home_and_selection_disable_pi_tracking(web_config):
    backend, app, _ = make_backend(camera_1="a", camera_2="b")
    backend.startup()
    control = Control()
    backend._pi_vision["a"] = control
    backend.set_auto_track(True)
    backend.home()
    assert not control.enabled
    backend.set_auto_track(True)
    backend.select(host="b")
    assert not control.enabled
    with pytest.raises(BackendError):
        backend.set_auto_track(True, "a")


def test_pi_connection_shutdown_closes_workers(web_config, monkeypatch):
    config.ROBOT_CONFIGS["a"] = robot("a", pi_vision_url="http://bluey.local:5051")
    monkeypatch.setattr(PiVisionControl, "start", lambda self: None)
    backend, _, _ = make_backend(camera_1="a")
    backend.startup()
    assert "a" in backend._pi_vision
    control = backend._pi_vision["a"]
    backend.assign_slots(None, None)
    assert control._quit.is_set()
    assert not backend._pi_vision


def test_commander_snapshot_contains_pi_skeleton_while_automation_is_off(web_config):
    backend, app, _ = make_backend(camera_1="a")
    app.frame = np.zeros((240, 320, 3), dtype=np.uint8)
    backend.startup()
    control = PiVisionControl(object(), SimpleNamespace(pi_vision_url="http://pi"), clock=lambda: 10)
    control.ingest({"schema_version": 1, "session_id": "pi", "enabled": True,
                    "sample": {"sequence": 1, "width": 640, "height": 480,
                               "age_s": .2, "inference_s": .17,
                               "detections": [{"box": [480, 50, 630, 400], "aim_point": [560, 170],
                                               "confidence": .9, "keypoints": [[520, 100, .9]] * 17}]}}, 10)
    backend._pi_vision["a"] = control
    client = TestClient(create_web_app(backend, static_dir=None))
    response = client.get("/api/cameras/a/snapshot")
    assert response.status_code == 200
    image = cv2.imdecode(np.frombuffer(response.content, np.uint8), cv2.IMREAD_COLOR)
    assert image[50, 260, 0] > 140 and image[50, 260, 1] > 140  # cyan pose point
    assert int(image[100, 240, 1]) > int(image[100, 240, 2]) + 30  # green bounding box
    assert not app.frame.any()
    assert not control.status()["enabled"]


def test_runtime_tuning_route_preserves_active_tracking_and_owner(web_config):
    backend, _, _ = make_backend(camera_1="a")
    backend.startup()
    requests = []
    def request(url, method, body):
        requests.append((url, method, body))
        return {"acceptable_ratio": body["acceptable_ratio"], "enabled": True, "owner": control.owner}
    control = PiVisionControl(object(), SimpleNamespace(pi_vision_url="http://pi"), request=request)
    control._enabled = control._armed = True
    backend._pi_vision["a"] = control
    client = TestClient(create_web_app(backend, static_dir=None))
    response = client.put("/api/control/pi-vision/tuning", json={"host": "a", "acceptable_ratio": .15})
    assert response.status_code == 200 and response.json() == {"acceptable_ratio": .15}
    assert requests == [("http://pi/api/v1/control/tuning", "PUT", {"owner": control.owner, "acceptable_ratio": .15})]
    assert control.status()["enabled"] and control._armed
    assert control.status()["acceptable_ratio"] == .15


@pytest.mark.parametrize("ratio", [.01, .9, None, True])
def test_runtime_tuning_route_rejects_invalid_tolerance(web_config, ratio):
    backend, _, _ = make_backend(camera_1="a")
    backend.startup()
    client = TestClient(create_web_app(backend, static_dir=None))
    assert client.put("/api/control/pi-vision/tuning", json={"acceptable_ratio": ratio}).status_code == 422


@pytest.mark.parametrize("code,reason", [(409, "another Commander owns autonomous control"),
                                         (409, "Tracking blocked until fresh measured joint telemetry is available."),
                                         (503, "Operator connection unavailable")])
def test_enable_tracking_returns_pi_rejection_detail_and_status(web_config, code, reason):
    from urllib.error import HTTPError
    backend, _, _ = make_backend(camera_1="a")
    backend.startup()
    requests = []
    def request(*args):
        requests.append(args)
        raise HTTPError("http://pi", code, reason, {}, None)
    control = PiVisionControl(object(), SimpleNamespace(pi_vision_url="http://pi"), request=request)
    backend._pi_vision["a"] = control
    client = TestClient(create_web_app(backend, static_dir=None))
    response = client.post("/api/control/auto-track", json={"enabled": True})
    assert response.status_code == code
    assert response.json()["detail"] == f"PiVision: {reason}"
    assert control.status()["last_thought"] == f"PiVision: {reason}"
    assert len(requests) == 1


def test_enable_tracking_transport_failure_is_not_reported_as_conflict(web_config):
    backend, _, _ = make_backend(camera_1="a")
    backend.startup()
    def request(*args):
        raise TimeoutError("connection timed out")
    control = PiVisionControl(object(), SimpleNamespace(pi_vision_url="http://pi"), request=request)
    backend._pi_vision["a"] = control
    client = TestClient(create_web_app(backend, static_dir=None))
    response = client.post("/api/control/auto-track", json={"enabled": True})
    assert response.status_code == 502
    assert response.json()["detail"] == "PiVision unreachable: connection timed out"
