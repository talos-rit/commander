"""Existing Commander command API through the Pi-local control gateway.

Operator supports one TCP client. PiVision owns that loopback connection; this
adapter avoids a competing Commander socket while preserving ICD payloads.
"""
import threading
import time

from loguru import logger

from src.connection.publisher import Publisher
from src.tracking.pi_vision import request_json


class EdgeTransport:
    def __init__(self, publisher):
        self.publisher = publisher

    def publish(self, command, payload=None):
        result = self.publisher._request("/api/v1/control/commands", "POST",
                                          {"command": int(command), "payload_hex": (payload or b"").hex()})
        if not result.get("dispatched"):
            raise RuntimeError("Pi gateway did not dispatch the command")
        return 0

    def add_message_listener(self, _listener):
        pass

    def is_connected(self):
        return self.publisher.is_connected()

    def close(self):
        self.publisher.close()


class EdgePublisher(Publisher):
    def __init__(self, url):
        # No TCP socket to Operator: only PiVision owns that single-client server.
        self.url = url.rstrip("/")
        self._erv_encoder_counts = self._erv_joint_counts = None
        self._erv_encoder_received_monotonic = self._erv_joint_received_monotonic = None
        self._telemetry_lock = threading.Lock()
        self._quit = threading.Event()
        self._connected = False
        self._last_status = 0.0
        self.operator_connection = EdgeTransport(self)
        self._thread = threading.Thread(target=self._poll, name="pi-operator-feedback", daemon=True)
        self._thread.start()

    def _request(self, path, method="GET", body=None):
        return request_json(self.url + path, method, body)

    def _poll(self):
        while not self._quit.is_set():
            try:
                state = self._request("/api/v1/control/status")
                now = time.monotonic()
                with self._telemetry_lock:
                    self._connected = bool(state.get("operator_connected"))
                    self._last_status = now
                    counts, age = state.get("joint_counts"), state.get("telemetry_age_s")
                    if counts is not None and len(counts) == 5 and age is not None:
                        self._erv_joint_counts = tuple(int(v) for v in counts)
                        self._erv_joint_received_monotonic = now - max(0, age)
            except Exception as error:
                with self._telemetry_lock:
                    self._connected = False
                logger.debug("Pi Operator feedback unavailable: {}", error)
            self._quit.wait(0.2)

    def is_connected(self):
        with self._telemetry_lock:
            return self._connected and time.monotonic() - self._last_status < 1.0

    def close(self):
        self._quit.set()
        if self._thread is not threading.current_thread():
            self._thread.join(timeout=1)
