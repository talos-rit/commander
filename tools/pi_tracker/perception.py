"""Latest-only, versioned perception contract. No robot commands live here."""
import threading
import time
import uuid


class PerceptionStore:
    def __init__(self):
        self.enabled = True
        self.session_id = uuid.uuid4().hex
        self._lock = threading.Lock()
        self._sample = None
        self._last_publish = None
        self._fps = 0.0

    def set_enabled(self, enabled):
        with self._lock:
            self.enabled = enabled
            self._sample = None
        return {"enabled": enabled}

    def publish(self, sample, detections, inference_s, *, pose_captured=None, motion_compensated=False):
        h, w = sample.frame.shape[:2]
        with self._lock:
            if not self.enabled:
                return
            now = time.monotonic()
            if self._last_publish is not None and now > self._last_publish:
                self._fps = 0.8 * self._fps + 0.2 / (now - self._last_publish)
            self._last_publish = now
            self._sample = {
                "sequence": sample.sequence,
                "captured": sample.captured_monotonic,
                "pose_captured": sample.captured_monotonic if pose_captured is None else pose_captured,
                "motion_compensated": motion_compensated,
                "width": w, "height": h,
                "inference_s": inference_s,
                "fps": self._fps,
                "detections": [{"box": d.box, "confidence": d.confidence,
                                "aim_point": d.center, "keypoints": d.keypoints}
                               for d in detections],
            }

    def snapshot(self):
        with self._lock:
            sample = self._sample
            payload = {"schema_version": 1, "session_id": self.session_id,
                       "enabled": self.enabled, "sample": None}
            if sample is not None:
                payload["sample"] = {k: v for k, v in sample.items() if k not in ("captured", "pose_captured")}
                payload["sample"]["age_s"] = max(0.0, time.monotonic() - sample["captured"])
                payload["sample"]["pose_age_s"] = max(0.0, time.monotonic() - sample["pose_captured"])
            return payload


class PerceptionOnlyOperator:
    """Explicitly inert diagnostic adapter; never opens an Operator socket."""
    is_connected = False
    host = "perception-only"
    port = 0

    def get_telemetry(self):
        # Imported lazily so perception startup remains independent of transport.
        try:
            from .operator_client import RobotTelemetry
        except ImportError:
            from operator_client import RobotTelemetry
        return RobotTelemetry()

    def get_fault(self):
        return "PiVision is perception-only; use Commander for robot control"

    def stop(self):
        pass
