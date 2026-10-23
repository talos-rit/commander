from types import SimpleNamespace

from src.tracking.pi_vision import PiVisionControl
from src.tracking.vertical import select_vertical_motion


def _motion(**overrides):
    values = dict(
        elbow=False,
        shoulder=False,
        polar_vertical=True,
        image_up=True,
        elbow_count=None,
        shoulder_count=None,
        pitch_count=None,
        counts_fresh=False,
        elbow_limits=None,
        shoulder_limits=None,
        pitch_limits=None,
    )
    values.update(overrides)
    return select_vertical_motion(**values)


def test_defaults_to_polar_up_and_keeps_a_disabled_axis_out():
    assert _motion() == ("polar", 1)
    assert _motion(polar_vertical=False) is None
    assert _motion(elbow=True, polar_vertical=False) == ("joint", 3, -1)
    assert _motion(elbow=True, shoulder=True, polar_vertical=False, image_up=False) == ("joint", 3, 1)


def test_fresh_limit_falls_through_and_stale_counts_do_not():
    blocked = dict(elbow=True, shoulder=True, polar_vertical=True, elbow_count=-20, elbow_limits=(-10, 10))
    assert _motion(**blocked, counts_fresh=True) == ("joint", 2, 1)
    assert _motion(**blocked, counts_fresh=False) == ("joint", 3, -1)
    held = {**blocked, "shoulder": False, "polar_vertical": False, "counts_fresh": True}
    assert _motion(**held) is None
    assert _motion(elbow=True, polar_vertical=True, elbow_count=10, elbow_limits=(-10, 10), counts_fresh=True, image_up=False) == ("polar", -1)


def test_lease_tells_the_pi_which_axes_are_allowed():
    calls = []

    def request(_url, method="GET", body=None):
        calls.append((method, body))
        return {"owner": control.owner, "enabled": body["enabled"], "lease_remaining_s": 1.5}

    robot = SimpleNamespace(
        pi_vision_url="http://pi:5051",
        pi_vision_speed_percent=20,
        pi_vision_max_age_s=0.35,
        track_elbow=True,
        track_shoulder=False,
        track_polar_vertical=False,
        elbow_count_min=-50,
        elbow_count_max=50,
    )
    control = PiVisionControl(object(), robot, request=request)
    assert control.set_enabled(True)
    axes = calls[0][1]["vertical_axes"]
    assert axes == {"elbow": True, "shoulder": False, "polar_vertical": False}
    assert calls[0][1]["elbow_limits"] == [-50, 50]
    assert "pitch_limits" not in calls[0][1]

    class OnePoll:
        def __init__(self):
            self.done = False
        def is_set(self):
            return self.done
        def wait(self, _seconds):
            self.done = True

    control._quit = OnePoll()
    control._poll()
    assert calls[-1][1]["renew"] is True
    assert calls[-1][1]["vertical_axes"]["elbow"] is True
