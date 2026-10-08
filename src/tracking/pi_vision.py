"""PiVision observation transport and Commander supervision of Pi-local control."""
from __future__ import annotations

import json
import math
import threading
import time
import uuid
import http.client
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


class PiVisionControl:
    """Commander supervision only. Every detection-to-motion step stays on Pi."""
    def __init__(self, publisher, robot_config, request=request_json, clock=time.monotonic):
        self.config, self.request, self.clock = robot_config, request, clock
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

    def _url(self, path):
        return self.config.pi_vision_url.rstrip("/") + path

    def start(self):
        self._thread = threading.Thread(target=self._poll, name="pivision-supervisor", daemon=True)
        self._thread.start()
        self._observation_thread = threading.Thread(target=self._poll_observations, name="pivision-observations", daemon=True)
        self._observation_thread.start()

    def ingest(self, payload, request_started):
        with self._lock:
            self._perception_enabled = payload.get("enabled") is True
        sample = validate_observations(payload)
        with self._lock:
            identity = (payload["session_id"], sample["sequence"])
            if self._identity is not None and identity[0] != self._identity[0]:
                self._enabled = False  # Pi restart requires explicit rearming.
            self._identity, self._sample = identity, sample
            self._capture = request_started - sample["age_s"]

    def _poll(self):
        while not self._quit.is_set():
            try:
                with self._lock:
                    if self._enabled:
                        self._edge = self.request(self._url("/api/v1/control/lease"), "PUT",
                                                  {"owner": self.owner, "enabled": True, "renew": True})
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

    def _poll_observations(self):
        while not self._quit.is_set():
            try:
                started = self.clock()
                self.ingest(self.request(self._url("/api/v1/observations")), started)
                with self._lock:
                    self._observation_error = None
            except Exception as error:
                with self._lock:
                    self._observation_error = str(error)
            self._quit.wait(0.1)

    def set_enabled(self, enabled):
        with self._lock:
            if not enabled and not self._armed:
                return False
            try:
                payload = {"owner": self.owner, "enabled": enabled}
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
        cv2.rectangle(canvas, (round(width * (1 - ratio) / 2), round(height * (1 - ratio) / 2)),
                      (round(width * (1 + ratio) / 2), round(height * (1 + ratio) / 2)), (255, 180, 0), 2)
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
        label = "PiVision | AUTO ON" if enabled else "PiVision | AUTO OFF"
        cv2.putText(canvas, label, (12, 26), cv2.FONT_HERSHEY_SIMPLEX, .65, (0, 0, 0), 4)
        cv2.putText(canvas, label, (12, 26), cv2.FONT_HERSHEY_SIMPLEX, .65, (0, 255, 255), 2)
        return canvas

    def close(self):
        self._quit.set()
        try:
            self.set_enabled(False)
        except ValueError:
            pass  # Lease expiry and Operator watchdog remain active on Pi.
        if self._thread is not None:
            self._thread.join(timeout=1)
        if self._observation_thread is not None:
            self._observation_thread.join(timeout=1)


