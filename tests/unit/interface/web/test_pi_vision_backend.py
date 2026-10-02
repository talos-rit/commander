import pytest

import src.config as config
from src.interface.web.backend import BackendError
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
