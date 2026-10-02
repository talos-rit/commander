"""PiVision observation transport and Commander supervision of Pi-local control."""
from __future__ import annotations

import json
import math
import threading
import time
import uuid
import http.client
import io
from urllib.error import HTTPError
from urllib.parse import urlsplit

_http_connections = threading.local()


def request_json(url, method="GET", body=None):
    data = None if body is None else json.dumps(body).encode()
    parsed = urlsplit(url)
    key = (parsed.scheme, parsed.hostname, parsed.port)
    cache = getattr(_http_connections, "cache", None)
    if cache is None:
        cache = _http_connections.cache = {}
    connection = cache.get(key)
    if connection is None:
        cls = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
        connection = cache[key] = cls(parsed.hostname, parsed.port, timeout=0.4)
    try:
        connection.request(method, parsed.path or "/", body=data, headers={"Content-Type": "application/json"})
        response = connection.getresponse()
        payload = response.read(256_001)
        if len(payload) > 256_000:
            raise ValueError("PiVision response exceeds observation limit")
        if response.status >= 400:
            raise HTTPError(url, response.status, response.reason, response.headers, io.BytesIO(payload))
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
        self._perception_enabled = None
        self._edge = {}
        self._thread = None

    def _url(self, path):
        return self.config.pi_vision_url.rstrip("/") + path

    def start(self):
        self._thread = threading.Thread(target=self._poll, name="pivision-supervisor", daemon=True)
        self._thread.start()

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
                        self._enabled = False
                        self._armed = False
                started = self.clock()
                self.ingest(self.request(self._url("/api/v1/observations")), started)
                with self._lock:
                    self._error = None
            except Exception as error:
                with self._lock:
                    self._error, self._enabled = str(error), False
                # No further renewals: the Pi's independent lease service stops it.
            self._quit.wait(0.2)

    def set_enabled(self, enabled):
        with self._lock:
            if not enabled and not self._armed:
                return False
            try:
                payload = {"owner": self.owner, "enabled": enabled}
                if enabled:
                    payload.update(speed_percent=getattr(self.config, "pi_vision_speed_percent", 20),
                                   max_observation_age_s=getattr(self.config, "pi_vision_max_age_s", 0.35))
                self._edge = self.request(self._url("/api/v1/control/lease"), "PUT",
                                          payload)
            except Exception as error:
                self._enabled = False
                raise ValueError(f"PiVision control unavailable: {error}") from error
            self._enabled = bool(self._edge.get("enabled")) and self._edge.get("owner") == self.owner
            self._armed = self._enabled
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

    def status(self):
        with self._lock:
            return {"source": "pivision", "control_location": "pi", "enabled": self._enabled,
                    "perception_enabled": self._perception_enabled, "error": self._error or self._edge.get("fault"),
                    "observation_age_s": self.clock() - self._capture if self._sample else None,
                    "inference_s": self._sample["inference_s"] if self._sample else None,
                    "fps": self._sample.get("fps", 0) if self._sample else 0,
                    "subjects": len(self._sample["detections"]) if self._sample else 0,
                    "sequence": self._identity[1] if self._identity else None}

    def close(self):
        self._quit.set()
        try:
            self.set_enabled(False)
        except ValueError:
            pass  # Lease expiry and Operator watchdog remain active on Pi.
        if self._thread is not None:
            self._thread.join(timeout=1)


