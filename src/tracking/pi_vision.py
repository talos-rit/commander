"""PiVision observation transport and Commander supervision of Pi-local control."""
from __future__ import annotations

import json
import math
import threading
import time
import uuid
import http.client
import socket
import io
import cv2
from urllib.error import HTTPError
from urllib.parse import urlsplit

_http_connections = threading.local()


class PiVisionRequestError(ValueError):
    def __init__(self, message, status):
        super().__init__(message)
        self.status = status


def request_json(url, method="GET", body=None):
    data = None if body is None else json.dumps(body).encode()
    parsed = urlsplit(url)
    key = (parsed.scheme, parsed.hostname, parsed.port)
    cache = getattr(_http_connections, "cache", None)
    if cache is None:
        cache = _http_connections.cache = {}
    last_used = getattr(_http_connections, "last_used", None)
    if last_used is None:
        last_used = _http_connections.last_used = {}
    connection = cache.get(key)
    if connection is not None and time.monotonic() - last_used.get(key, 0) > 2:
        connection.close()
        cache.pop(key, None)
        connection = None
    if connection is None:
        cls = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
        connection = cache[key] = cls(parsed.hostname, parsed.port, timeout=0.4)
    try:
        connection.request(method, parsed.path or "/", body=data, headers={"Content-Type": "application/json"})
        response = connection.getresponse()
        payload = response.read(256_001)
        last_used[key] = time.monotonic()
        if len(payload) > 256_000:
            raise ValueError("PiVision response exceeds observation limit")
        if response.status >= 400:
            reason = response.reason
            try:
                detail = json.loads(payload).get("detail")
                if isinstance(detail, str) and detail:
                    reason = detail[:2000]
            except (ValueError, AttributeError, UnicodeError):
                pass
            raise HTTPError(url, response.status, reason, response.headers, io.BytesIO(payload))
        return json.loads(payload)
    except Exception:
        connection.close()
        cache.pop(key, None)
        raise


def stream_json_events(url, read_timeout=2.5, max_event_bytes=256_000, on_open=None):
    """Yield each JSON `data:` payload of a server-sent event stream.

    Uses its own connection: a stream holds a socket open indefinitely, so it can't
    share `request_json`'s keep-alive cache. PiVision heartbeats every second, so a
    read that times out means the stream is dead and the caller should reconnect.
    `on_open(sock)` hands over the socket so another thread can shut it to stop at once.
    """
    parsed = urlsplit(url)
    cls = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    connection = cls(parsed.hostname, parsed.port, timeout=read_timeout)
    try:
        connection.connect()
        if on_open is not None:
            # The socket itself: http.client may detach it from `connection` mid-response.
            on_open(connection.sock)
        connection.request("GET", parsed.path or "/", headers={"Accept": "text/event-stream"})
        response = connection.getresponse()
        if response.status >= 400:
            raise HTTPError(url, response.status, response.reason, response.headers, io.BytesIO(response.read(2000)))
        data = []
        while True:
            line = response.readline(max_event_bytes + 2)
            if not line:
                raise ConnectionError("PiVision closed the observation stream")
            if len(line) > max_event_bytes or sum(map(len, data)) > max_event_bytes:
                raise ValueError("PiVision event exceeds observation limit")
            line = line.rstrip(b"\r\n")
            if line.startswith(b"data:"):
                data.append(line[5:].lstrip(b" "))
            elif not line and data:
                yield json.loads(b"\n".join(data))
                data = []
    finally:
        connection.close()


def validate_observations(payload):
    if payload.get("schema_version") != 1 or not isinstance(payload.get("session_id"), str):
        raise ValueError("unsupported PiVision observation schema")
    if payload.get("enabled") is not True or payload.get("sample") is None:
        raise ValueError("PiVision perception is paused or awaiting a frame")
    sample = payload["sample"]
    for name in ("sequence", "width", "height"):
        if type(sample.get(name)) is not int or sample[name] < (0 if name == "sequence" else 1):
            raise ValueError(f"invalid observation {name}")
    for name in ("age_s", "inference_s"):
        value = sample.get(name)
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError(f"invalid observation {name}")
    detections = sample.get("detections")
    if not isinstance(detections, list) or len(detections) > 100:
        raise ValueError("invalid detections")
    for detection in detections:
        for name, length in (("box", 4), ("aim_point", 2)):
            values = detection.get(name)
            if not isinstance(values, (list, tuple)) or len(values) != length or any(
                not isinstance(v, (int, float)) or not math.isfinite(v) for v in values
            ):
                raise ValueError(f"invalid detection {name}")
        x, y = detection["aim_point"]
        x1, y1, x2, y2 = detection["box"]
        confidence = detection.get("confidence")
        if not (0 <= x < sample["width"] and 0 <= y < sample["height"]
                and 0 <= x1 < x2 <= sample["width"] and 0 <= y1 < y2 <= sample["height"]
                and isinstance(confidence, (int, float)) and math.isfinite(confidence) and 0 <= confidence <= 1):
            raise ValueError("detection outside image or invalid confidence")
        points = detection.get("keypoints")
        if points is not None and (not isinstance(points, (list, tuple)) or len(points) != 17 or any(
                not isinstance(p, (list, tuple)) or len(p) != 3 or any(
                    not isinstance(v, (int, float)) or not math.isfinite(v) for v in p
                ) or not 0 <= p[2] <= 1 for p in points)):
            raise ValueError("invalid pose keypoints")
    return sample


class SubjectIds:
    """IDs for Pi detections that persist across samples.

    The Pi sends boxes without tracker IDs, so each new box takes the ID of the
    nearest box from recent samples, within `max_jump` of the image width.
    """

    def __init__(self, max_jump=0.2, forget_s=1.5):
        self.max_jump, self.forget_s = max_jump, forget_s
        self._tracks = {}  # id -> (center_x, center_y, last_seen)
        self._next = 1

    def reset(self):
        self._tracks.clear()

    def assign(self, boxes, width, now):
        self._tracks = {i: t for i, t in self._tracks.items() if now - t[2] <= self.forget_s}
        centers = [((x1 + x2) / 2, (y1 + y2) / 2) for x1, y1, x2, y2 in boxes]
        pairs = sorted(
            (math.dist(center, track[:2]), index, track_id)
            for index, center in enumerate(centers)
            for track_id, track in self._tracks.items()
        )
        matched, used = {}, set()
        for distance, index, track_id in pairs:
            if distance > self.max_jump * width:
                break
            if index not in matched and track_id not in used:
                matched[index] = track_id
                used.add(track_id)
        ids = []
        for index, center in enumerate(centers):
            track_id = matched.get(index)
            if track_id is None:
                track_id, self._next = self._next, self._next + 1
            self._tracks[track_id] = (*center, now)
            ids.append(track_id)
        return ids


class PiVisionControl:
    """Commander supervision only. Every detection-to-motion step stays on Pi."""
    STREAM_RETRY_S = 30.0  # How long to poll a PiVision without the stream before asking again.

    def __init__(self, publisher, robot_config, request=request_json, clock=time.monotonic,
                 on_observations=None, stream=stream_json_events):
        self.config, self.request, self.clock, self.stream = robot_config, request, clock, stream
        # Called with (detections with "id" added, (width, height)) per sample, or
        # (None, None) once observations stop. Runs on the polling thread.
        self.on_observations = on_observations
        self._ids = SubjectIds()
        self.owner = uuid.uuid4().hex
        self._lock = threading.RLock()
        self._quit = threading.Event()
        self._enabled = False
        self._armed = False
        self._sample = None
        self._identity = None
        self._capture = 0.0
        self._error = None
        self._observation_error = None
        self._stop_reason = None
        self._lease_deadline = 0.0
        self._acceptable_ratio = getattr(robot_config, "acceptable_box_percent", .25)
        self._perception_enabled = None
        self._edge = {}
        self._thread = None
        self._observation_thread = None
        self._process_thread = None
        # Latest-only handoff from the reader to the processor: the stream delivers every
        # sample, but processing one can take longer than the next takes to arrive.
        self._latest = None  # (fetch, received_at)
        self._latest_ready = threading.Event()
        self._stream_socket = None

    def _url(self, path):
        return self.config.pi_vision_url.rstrip("/") + path

    def start(self):
        self._thread = threading.Thread(target=self._poll, name="pivision-supervisor", daemon=True)
        self._thread.start()
        self._observation_thread = threading.Thread(target=self._watch_observations, name="pivision-observations", daemon=True)
        self._observation_thread.start()
        self._process_thread = threading.Thread(target=self._process_observations, name="pivision-observation-processing", daemon=True)
        self._process_thread.start()

    def ingest(self, payload, request_started):
        with self._lock:
            self._perception_enabled = payload.get("enabled") is True
        sample = validate_observations(payload)
        with self._lock:
            identity = (payload["session_id"], sample["sequence"])
            if self._identity is not None and identity[0] != self._identity[0]:
                self._enabled = False  # Pi restart requires explicit rearming.
                self._ids.reset()
            if identity == self._identity:
                return  # Same sample polled again; keep its IDs.
            ids = self._ids.assign([d["box"] for d in sample["detections"]], sample["width"], self.clock())
            sample = {**sample, "detections": [{**d, "id": i} for d, i in zip(sample["detections"], ids)]}
            self._identity, self._sample = identity, sample
            self._capture = request_started - sample["age_s"]
        if self.on_observations is not None:
            self.on_observations(sample["detections"], (sample["width"], sample["height"]))

    def _poll(self):
        while not self._quit.is_set():
            try:
                with self._lock:
                    if self._enabled:
                        self._edge = self.request(self._url("/api/v1/control/lease"), "PUT",
                                                  self._lease_body(True, renew=True))
                    else:
                        self._edge = self.request(self._url("/api/v1/control/status"))
                    if self._edge.get("owner") != self.owner or not self._edge.get("enabled"):
                        if self._enabled:
                            self._stop_reason = self._edge.get("last_thought") or "PiVision control was stopped; explicitly rearm"
                        self._enabled = False
                        self._armed = False
                    else:
                        self._lease_deadline = self.clock() + self._edge.get("lease_remaining_s", 1.5)
                    self._error = None
            except Exception as error:
                with self._lock:
                    self._error = str(error)
                    # Retry transport failures within the existing lease. A diagnostic
                    # timeout must not disarm local control; a revoked/expired lease
                    # still requires explicit rearming and can never be reacquired here.
                    if isinstance(error, HTTPError) or self.clock() >= self._lease_deadline:
                        if self._enabled:
                            self._stop_reason = f"Tracking stopped: {error}; explicitly rearm"
                        self._enabled = False
            self._quit.wait(0.2)

    def _watch_observations(self):
        """Follow PiVision's observation stream, polling instead on a PiVision without one.

        Only reads: each payload overwrites the latest-only slot that
        `_process_observations` consumes, so a slow consumer skips samples rather
        than falling behind a backlog of them.
        """
        while not self._quit.is_set():
            try:
                for payload in self.stream(self._url("/api/v1/observations/stream"), on_open=self._stream_opened):
                    self._offer(lambda payload=payload: payload, self.clock())
                    if self._quit.is_set():
                        return
                self._quit.wait(0.5)  # Stream ended without an error; reconnect.
            except HTTPError as error:
                if error.code != 404:
                    self._observation_failed(error)
                    self._quit.wait(0.5)
                    continue
                deadline = self.clock() + self.STREAM_RETRY_S
                while not self._quit.is_set() and self.clock() < deadline:
                    self._poll_observations()
            except Exception as error:
                self._observation_failed(error)
                self._quit.wait(0.5)

    def _stream_opened(self, sock):
        self._stream_socket = sock
        if self._quit.is_set():  # Stopped while connecting.
            self._close_stream()

    def _close_stream(self):
        sock = self._stream_socket
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)  # Wakes a reader blocked in recv.
            except OSError:
                pass

    def _poll_observations(self):
        """One poll of the JSON endpoint, for a PiVision that predates the stream."""
        started = self.clock()
        try:
            payload = self.request(self._url("/api/v1/observations"))
        except Exception as error:
            self._observation_failed(error)
        else:
            self._offer(lambda: payload, started)
        self._quit.wait(0.1)

    def _offer(self, fetch, received_at):
        with self._lock:
            self._latest = (fetch, received_at)
        self._latest_ready.set()

    def _process_observations(self):
        while not self._quit.is_set():
            if self._latest_ready.wait(0.5):
                self._process_latest()

    def _process_latest(self):
        """Ingest the newest offered payload, if any; older unprocessed ones are dropped."""
        with self._lock:
            latest, self._latest = self._latest, None
            self._latest_ready.clear()
        if latest is None:
            return
        fetch, received_at = latest
        try:
            self.ingest(fetch(), received_at)
            with self._lock:
                self._observation_error = None
        except Exception as error:
            self._observation_failed(error)

    def _observation_failed(self, error):
        with self._lock:
            self._observation_error = str(error)
            stale = self._sample is None or self.clock() - self._capture > 1.0
        if stale and self.on_observations is not None:
            self.on_observations(None, None)

    def set_enabled(self, enabled):
        with self._lock:
            if not enabled and not self._armed:
                return False
            try:
                payload = self._lease_body(enabled)
                if enabled:
                    payload.update(speed_percent=getattr(self.config, "pi_vision_speed_percent", 20),
                                   max_observation_age_s=getattr(self.config, "pi_vision_max_age_s", 0.35),
                                   acceptable_ratio=self._acceptable_ratio)
                self._edge = self.request(self._url("/api/v1/control/lease"), "PUT",
                                          payload)
            except HTTPError as error:
                self._enabled = False
                self._stop_reason = f"PiVision: {error.reason}"
                raise PiVisionRequestError(self._stop_reason, error.code) from error
            except Exception as error:
                self._enabled = False
                self._stop_reason = f"PiVision unreachable: {error}"
                raise PiVisionRequestError(self._stop_reason, 502) from error
            self._enabled = bool(self._edge.get("enabled")) and self._edge.get("owner") == self.owner
            self._armed = self._enabled
            self._lease_deadline = self.clock() + self._edge.get("lease_remaining_s", 1.5) if self._enabled else 0
            self._stop_reason = None
            return self._enabled

    def _lease_body(self, enabled, renew=False):
        """Arm, renew, or release. Vertical axes ride along so the Pi decides the jog locally."""
        payload = {"owner": self.owner, "enabled": enabled}
        if renew:
            payload["renew"] = True
        if not enabled:
            return payload
        config = self.config

        def pair(low_name, high_name):
            low, high = getattr(config, low_name, None), getattr(config, high_name, None)
            if low is None or high is None:
                return None
            return [int(low), int(high)]

        payload["vertical_axes"] = {
            "elbow": bool(getattr(config, "track_elbow", False)),
            "shoulder": bool(getattr(config, "track_shoulder", False)),
            "polar_vertical": bool(getattr(config, "track_polar_vertical", True)),
        }
        payload["elbow_limits"] = pair("elbow_count_min", "elbow_count_max")
        payload["shoulder_limits"] = pair("shoulder_count_min", "shoulder_count_max")
        pitch = pair("pitch_count_min", "pitch_count_max")
        if pitch is not None:
            payload["pitch_limits"] = pitch
        return payload

    def manual_handoff(self):
        pass  # The Pi command gateway performs arbitration next to Operator.

    def set_perception(self, enabled):
        if not enabled:
            self.set_enabled(False)
        response = self.request(self._url("/api/v1/perception"), "PUT", {"enabled": enabled})
        with self._lock:
            self._perception_enabled = response.get("enabled") is True
        return response

    def set_tolerance(self, ratio):
        if type(ratio) not in (int, float) or not .05 <= ratio <= .8:
            raise ValueError("centering tolerance must be 0.05..0.8")
        with self._lock:
            self._edge = self.request(self._url("/api/v1/control/tuning"), "PUT",
                                      {"owner": self.owner, "acceptable_ratio": ratio})
            self._acceptable_ratio = ratio
            return {"acceptable_ratio": self._edge["acceptable_ratio"]}

    def status(self):
        with self._lock:
            return {"source": "pivision", "control_location": "pi", "enabled": self._enabled,
                    "perception_enabled": self._perception_enabled, "error": self._error or self._observation_error or self._edge.get("fault"),
                    "robot_fault": self._edge.get("fault") or (
                        self._edge.get("last_thought") or "Controller error" if self._edge.get("state") == "FAULT" else None),
                    "state": self._edge.get("state"), "last_thought": self._stop_reason or self._edge.get("last_thought"),
                    "acceptable_ratio": self._edge.get("acceptable_ratio", self._acceptable_ratio),
                    "observation_age_s": self.clock() - self._capture if self._sample else None,
                    "inference_s": self._sample["inference_s"] if self._sample else None,
                    "fps": self._sample.get("fps", 0) if self._sample else 0,
                    "subjects": len(self._sample["detections"]) if self._sample else 0,
                    "sequence": self._identity[1] if self._identity else None}

    def annotate_frame(self, frame):
        with self._lock:
            sample = self._sample
            fresh = self._perception_enabled and sample is not None and self.clock() - self._capture <= 1.0
            enabled = self._enabled
            ratio = self._edge.get("acceptable_ratio", self._acceptable_ratio)
        canvas = frame.copy()
        if not fresh:
            return canvas
        height, width = canvas.shape[:2]
        center_x, center_y = width // 2, height // 3
        box_width, box_height = int(width * ratio), int(height * ratio)
        cv2.rectangle(canvas, (center_x - box_width // 2, center_y - box_height // 2),
                      (center_x + box_width // 2, center_y + box_height // 2), (255, 180, 0), 2)
        sx, sy = width / sample["width"], height / sample["height"]
        def point(x, y):
            return (max(0, min(width - 1, round(x * sx))), max(0, min(height - 1, round(y * sy))))
        for detection in sample["detections"]:
            x1, y1, x2, y2 = detection["box"]
            cv2.rectangle(canvas, point(x1, y1), point(x2, y2), (0, 255, 0), 2)
            points = detection.get("keypoints")
            if points:
                for a, b in ((0,1),(0,2),(1,3),(2,4),(5,6),(5,7),(7,9),(6,8),(8,10),(5,11),(6,12),(11,12),(11,13),(13,15),(12,14),(14,16)):
                    if points[a][2] >= .3 and points[b][2] >= .3:
                        cv2.line(canvas, point(*points[a][:2]), point(*points[b][:2]), (255, 255, 0), 2)
                for x, y, confidence in points:
                    if confidence >= .3:
                        cv2.circle(canvas, point(x, y), 3, (255, 255, 0), -1)
            cv2.circle(canvas, point(*detection["aim_point"]), 5, (0, 165, 255), -1)
            if detection.get("id") is not None:
                left, top = point(x1, y1)
                cv2.putText(canvas, f"#{detection['id']}", (left + 4, max(16, top - 6)),
                            cv2.FONT_HERSHEY_SIMPLEX, .6, (0, 255, 0), 2)
        label = "PiVision | AUTO ON" if enabled else "PiVision | AUTO OFF"
        cv2.putText(canvas, label, (12, 26), cv2.FONT_HERSHEY_SIMPLEX, .65, (0, 0, 0), 4)
        cv2.putText(canvas, label, (12, 26), cv2.FONT_HERSHEY_SIMPLEX, .65, (0, 255, 255), 2)
        return canvas

    def request_stop(self):
        """Tell the threads to finish without waiting; close() still disarms and joins.

        Shuts the observation stream's socket so its reader wakes now instead of at
        the next heartbeat, and wakes the processor.
        """
        self._quit.set()
        self._latest_ready.set()
        self._close_stream()

    def close(self):
        self.request_stop()
        try:
            self.set_enabled(False)
        except ValueError:
            pass  # Lease expiry and Operator watchdog remain active on Pi.
        if self._thread is not None:
            self._thread.join(timeout=1)
        if self._observation_thread is not None:
            self._observation_thread.join(timeout=1)
        if self._process_thread is not None:
            self._process_thread.join(timeout=1)

