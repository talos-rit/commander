from types import SimpleNamespace
import pytest
from src.tracking.pi_vision import PiVisionControl, validate_observations

def observation():
    return {"schema_version": 1, "session_id": "camera-a", "enabled": True,
            "sample": {"sequence": 1, "width": 640, "height": 480, "age_s": 0.2,
                       "inference_s": 0.17, "detections": [{"box": [480, 50, 630, 400],
                       "confidence": 0.9, "aim_point": [560, 170]}]}}

def test_supervisor_never_sends_per_frame_motion():
    calls = []
    def request(url, method="GET", body=None):
        calls.append((url, method, body))
        return {"owner": control.owner, "enabled": body["enabled"]}
    control = PiVisionControl(object(), SimpleNamespace(pi_vision_url="http://pi:5051"), request=request)
    control.ingest(observation(), 10)
    assert control.set_enabled(True)
    assert calls[0][0].endswith("/api/v1/control/lease")
    assert calls[0][2]["owner"] == control.owner and calls[0][2]["enabled"]
    control.close()
    assert calls[-1][2]["enabled"] is False

def test_restart_clears_local_arming():
    control = PiVisionControl(object(), SimpleNamespace(pi_vision_url="http://pi"))
    control.ingest(observation(), 10)
    control._enabled = True
    restarted = observation()
    restarted["session_id"] = "camera-b"
    control.ingest(restarted, 11)
    assert not control.status()["enabled"]

@pytest.mark.parametrize("mutate", [
    lambda p: p.update(schema_version=2),
    lambda p: p["sample"].update(age_s=float("nan")),
    lambda p: p["sample"].update(sequence=-1),
    lambda p: p["sample"]["detections"][0].update(aim_point=[700, 30]),
    lambda p: p["sample"]["detections"][0].update(confidence=2),
])
def test_invalid_observations_rejected(mutate):
    payload = observation()
    mutate(payload)
    with pytest.raises(ValueError):
        validate_observations(payload)
