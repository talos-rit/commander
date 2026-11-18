import time
from types import SimpleNamespace
import numpy as np
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


def test_pose_overlay_scales_coordinates_without_changing_capture_frame():
    payload = observation()
    payload["sample"]["detections"][0]["keypoints"] = [[520, 100, .9]] * 17
    control = PiVisionControl(object(), SimpleNamespace(pi_vision_url="http://pi"), clock=lambda: 10)
    control.ingest(payload, 10)
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    annotated = control.annotate_frame(frame)
    assert not frame.any()
    assert annotated[50, 260].any()  # skeleton at half-size, independent of motion enable
    assert annotated[25, 240].any()  # bounding box corner
    control._capture = 8
    assert not control.annotate_frame(frame).any()  # do not show an old skeleton as current


def test_commander_overlay_places_tracking_region_in_upper_third():
    control = PiVisionControl(object(), SimpleNamespace(pi_vision_url="http://pi"), clock=lambda: 10)
    control.ingest(observation(), 10)
    frame = np.zeros((240, 320, 3), dtype=np.uint8)

    annotated = control.annotate_frame(frame)

    assert tuple(annotated[50, 160]) == (255, 180, 0)
    assert not annotated[90, 160].any()


class OnePoll:
    def __init__(self):
        self.done = False
    def is_set(self):
        return self.done
    def wait(self, _):
        self.done = True


def test_observation_timeout_does_not_disable_local_control():
    def request(*args):
        raise TimeoutError("diagnostic read timed out")
    control = PiVisionControl(object(), SimpleNamespace(pi_vision_url="http://pi"), request=request)
    control._enabled = True
    control._quit = OnePoll()
    control._poll_observations()
    assert control.status()["enabled"]
    assert "diagnostic" in control.status()["error"]


@pytest.mark.parametrize("now,enabled", [(10, True), (12, False)])
def test_renewal_transport_timeout_retries_only_within_existing_lease(now, enabled):
    requests = []
    def request(url, method, body):
        requests.append(body)
        raise TimeoutError("renewal timeout")
    control = PiVisionControl(object(), SimpleNamespace(pi_vision_url="http://pi"), request=request, clock=lambda: now)
    control._enabled = True
    control._lease_deadline = 11
    control._quit = OnePoll()
    control._poll()
    assert control.status()["enabled"] is enabled
    assert requests[0]["renew"] is True


def test_revoked_lease_stops_immediately_and_keeps_reason_after_status_recovers():
    from urllib.error import HTTPError
    def request(*args):
        raise HTTPError("http://pi", 409, "lease revoked", {}, None)
    control = PiVisionControl(object(), SimpleNamespace(pi_vision_url="http://pi"), request=request, clock=lambda: 10)
    control._enabled = True
    control._lease_deadline = 11
    control._quit = OnePoll()
    control._poll()
    assert not control.status()["enabled"]
    control._error = None
    assert "lease revoked" in control.status()["last_thought"]


def test_http_rejection_keeps_pi_controller_reason(monkeypatch):
    import json
    import src.tracking.pi_vision as module
    from urllib.error import HTTPError
    detail = "Tracking blocked until fresh measured joint telemetry is available."
    payload = json.dumps({"detail": detail}).encode()
    response = SimpleNamespace(status=409, reason="Conflict", headers={}, read=lambda _: payload)
    connection = SimpleNamespace(request=lambda *args, **kwargs: None,
                                 getresponse=lambda: response, close=lambda: None)
    monkeypatch.setattr(module, "_http_connections", SimpleNamespace())
    monkeypatch.setattr(module.http.client, "HTTPConnection", lambda *args, **kwargs: connection)
    with pytest.raises(HTTPError) as error:
        module.request_json("http://pi/api/v1/control/lease", "PUT", {"enabled": True})
    assert error.value.code == 409
    assert detail in str(error.value)
    assert error.value.read() == payload
    assert not module._http_connections.cache


def test_idle_connection_is_replaced_before_sending_control_command(monkeypatch):
    import src.tracking.pi_vision as module
    calls = []
    key = ("http", "pi", None)
    stale = SimpleNamespace(close=lambda: calls.append("closed"))
    response = SimpleNamespace(status=200, read=lambda _: b'{"dispatched":true}')
    fresh = SimpleNamespace(request=lambda *args, **kwargs: calls.append("sent"),
                            getresponse=lambda: response)
    monkeypatch.setattr(module, "_http_connections", SimpleNamespace(cache={key: stale}, last_used={key: 0}))
    monkeypatch.setattr(module.time, "monotonic", lambda: 10)
    monkeypatch.setattr(module.http.client, "HTTPConnection", lambda *args, **kwargs: fresh)
    assert module.request_json("http://pi/api/v1/control/commands", "POST", {}) == {"dispatched": True}
    assert calls == ["closed", "sent"]


def test_controller_fault_is_reported_separately_from_network_error():
    control = PiVisionControl(object(), SimpleNamespace(pi_vision_url="http://pi"))
    control._edge = {"state": "FAULT", "last_thought": "Controller rejected command"}
    assert control.status()["robot_fault"] == "Controller rejected command"
    control._edge = {"state": "DISABLED"}
    control._error = "getaddrinfo failed"
    assert control.status()["robot_fault"] is None


def sample_with(boxes, sequence):
    payload = observation()
    payload["sample"]["sequence"] = sequence
    payload["sample"]["detections"] = [
        {"box": box, "confidence": 0.8, "aim_point": [(box[0] + box[2]) // 2, box[1] + 10]}
        for box in boxes
    ]
    return payload


def test_subject_ids_persist_as_people_move_and_swap_order():
    seen = []
    control = PiVisionControl(object(), SimpleNamespace(pi_vision_url="http://pi"), clock=lambda: 10,
                              on_observations=lambda detections, size: seen.append((detections, size)))
    control.ingest(sample_with([[100, 50, 200, 400], [400, 50, 500, 400]], 1), 10)
    # Both move a little, and the Pi now lists them in the other order.
    control.ingest(sample_with([[420, 50, 520, 400], [110, 50, 210, 400]], 2), 10)

    first, second = (detections for detections, _ in seen)
    assert [d["id"] for d in first] == [1, 2]
    assert [d["id"] for d in second] == [2, 1]
    assert seen[0][1] == (640, 480)


def test_repeated_sample_keeps_ids_and_is_not_republished():
    seen = []
    control = PiVisionControl(object(), SimpleNamespace(pi_vision_url="http://pi"),
                              on_observations=lambda detections, size: seen.append(detections))
    control.ingest(sample_with([[100, 50, 200, 400]], 1), 10)
    control.ingest(sample_with([[100, 50, 200, 400]], 1), 10.1)

    assert len(seen) == 1


def test_a_far_jump_is_a_new_subject():
    control = PiVisionControl(object(), SimpleNamespace(pi_vision_url="http://pi"), clock=lambda: 10)
    control.ingest(sample_with([[0, 50, 60, 400]], 1), 10)
    control.ingest(sample_with([[560, 50, 630, 400]], 2), 10)

    assert control._sample["detections"][0]["id"] == 2


def test_stale_observations_clear_subjects(monkeypatch):
    seen = []
    now = [10.0]
    def request(url, method="GET", body=None):
        raise TimeoutError("pi slow")
    control = PiVisionControl(object(), SimpleNamespace(pi_vision_url="http://pi"), request=request,
                              clock=lambda: now[0], on_observations=lambda d, s: seen.append((d, s)))
    control.ingest(sample_with([[100, 50, 200, 400]], 1), 10)
    now[0] = 12.0
    control._quit = OnePoll()
    control._poll_observations()

    assert seen[-1] == (None, None)


def test_stream_backlog_is_skipped_so_only_the_newest_sample_is_processed():
    seen = []
    events = [sample_with([[100, 50, 200, 400]], n) for n in (1, 2, 3)]
    control = PiVisionControl(object(), SimpleNamespace(pi_vision_url="http://pi"),
                              stream=lambda url, **_: iter(events), on_observations=lambda d, s: seen.append(d))
    control._quit = OnePoll()
    control._watch_observations()  # Reads all three before the processor runs.
    control._process_latest()
    control._process_latest()  # Nothing new: a no-op, not a repeat.

    assert len(seen) == 1
    assert control.status()["sequence"] == 3 and control.status()["error"] is None


def test_paused_sample_is_reported_without_stopping_the_stream():
    paused = {**observation(), "enabled": False, "sample": None}
    control = PiVisionControl(object(), SimpleNamespace(pi_vision_url="http://pi"),
                              stream=lambda url, **_: iter([paused]))
    control._quit = OnePoll()
    control._watch_observations()
    control._process_latest()

    assert "paused" in control.status()["error"]


def test_older_pivision_without_stream_falls_back_to_polling():
    from urllib.error import HTTPError
    polled = []
    def stream(url, **_):
        raise HTTPError(url, 404, "Not Found", None, None)
    def request(url, method="GET", body=None):
        polled.append(url)
        return observation()
    control = PiVisionControl(object(), SimpleNamespace(pi_vision_url="http://pi"), request=request, stream=stream)
    control._quit = OnePoll()
    control._watch_observations()
    control._process_latest()

    assert polled == ["http://pi/api/v1/observations"]
    assert control.status()["sequence"] == 1


def test_dropped_stream_reports_error_and_clears_stale_subjects():
    seen = []
    now = [10.0]
    def stream(url, **_):
        yield sample_with([[100, 50, 200, 400]], 1)
        now[0] = 12.0
        raise TimeoutError("stream read timed out")
    control = PiVisionControl(object(), SimpleNamespace(pi_vision_url="http://pi"), stream=stream,
                              clock=lambda: now[0], on_observations=lambda d, s: seen.append(d))
    control._quit = OnePoll()
    control._watch_observations()

    assert seen[-1] is None
    assert "timed out" in control.status()["error"]


def test_stream_json_events_parses_server_sent_events():
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from src.tracking.pi_vision import stream_json_events

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(b': comment\n\ndata: {"a": 1}\n\ndata: {"b":\ndata: 2}\n\n')

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        events = stream_json_events(f"http://127.0.0.1:{server.server_port}/s", read_timeout=2)
        assert next(events) == {"a": 1}
        assert next(events) == {"b": 2}
        with pytest.raises(ConnectionError):
            next(events)
    finally:
        server.shutdown()


def test_request_stop_wakes_a_reader_blocked_on_the_stream():
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from src.tracking.pi_vision import stream_json_events

    class Silent(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.flush()
            time.sleep(3)  # Never sends an event, like a stream between heartbeats.

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Silent)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    control = PiVisionControl(object(), SimpleNamespace(pi_vision_url=f"http://127.0.0.1:{server.server_port}"),
                              stream=lambda url, **kw: stream_json_events(url, read_timeout=5, **kw))
    reader = threading.Thread(target=control._watch_observations, daemon=True)
    try:
        reader.start()
        deadline = time.monotonic() + 2
        while control._stream_socket is None and time.monotonic() < deadline:
            time.sleep(0.01)
        time.sleep(0.1)  # Let it block in recv.
        started = time.monotonic()
        control.request_stop()
        reader.join(timeout=2)
        assert not reader.is_alive() and time.monotonic() - started < 0.5
    finally:
        server.shutdown()
