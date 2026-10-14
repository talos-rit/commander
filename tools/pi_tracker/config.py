# Pi Edge Tracker & Closed-Loop Controller Configuration

import os
from dataclasses import dataclass


def _optional_int(name: str) -> int | None:
    value = os.getenv(name)
    return int(value) if value not in (None, "") else None


@dataclass
class TrackerConfig:
    # Camera Stream Source: RTSP stream from camera-streamer on localhost, or local device index
    camera_source: str = os.getenv("CAMERA_SOURCE", "rtsp://localhost:8554/camera")
    
    # Target frame dimensions for inference (320x320 square for YOLO)
    inference_width: int = int(os.getenv("INFERENCE_WIDTH", "320"))
    inference_height: int = int(os.getenv("INFERENCE_HEIGHT", "320"))
    
    # Model configuration
    model_weights: str = os.getenv("POSE_MODEL", "yolo11n-pose-320.onnx")
    confidence_threshold: float = float(os.getenv("CONF_THRESHOLD", "0.35"))
    target_class_id: int = 0  # 0 is 'person' in COCO
    allow_detector_fallback: bool = os.getenv("ALLOW_DETECTOR_FALLBACK", "0") == "1"
    # Read-only expression diagnostics. No expression result controls hardware.
    
    # Operator TCP Connection (Localhost on Bluey)
    operator_host: str = os.getenv("OPERATOR_HOST", "127.0.0.1")
    operator_port: int = int(os.getenv("OPERATOR_PORT", "61616"))
    
    # Closed-loop tracking parameters (Conservative to prevent overshoot)
    default_speed_percent: int = int(os.getenv("DEFAULT_SPEED", "20"))       # 20% gentle tracking speed
    acceptable_box_ratio: float = float(os.getenv("DEADBAND_RATIO", "0.25"))
    control_rate_hz: float = float(os.getenv("CONTROL_RATE_HZ", "60.0"))
    target_lost_timeout_s: float = float(os.getenv("TARGET_LOST_TIMEOUT", "0.35"))
    telemetry_timeout_s: float = float(os.getenv("TELEMETRY_TIMEOUT", "1.25"))
    max_observation_age_s: float = float(os.getenv("MAX_OBSERVATION_AGE", "0.35"))
    settle_time_s: float = float(os.getenv("SETTLE_TIME", "0.12"))
    min_pulse_s: float = float(os.getenv("MIN_PULSE", "0.055"))
    min_pitch_pulse_s: float = float(os.getenv("MIN_PITCH_PULSE", "0.045"))
    max_base_pulse_s: float = float(os.getenv("MAX_BASE_PULSE", "0.16"))
    max_pitch_pulse_s: float = float(os.getenv("MAX_PITCH_PULSE", "0.09"))
    
    # Autocorrection & Joint safety limits (from Bluey calibration)
    enable_joint_limits: bool = True
    base_min_count: int = -5000
    base_max_count: int = 5000
    # Optional extra count limits; pitch uses Operator's existing wrist-pitch path.
    pitch_min_count: int | None = _optional_int("PITCH_MIN_COUNT")
    pitch_max_count: int | None = _optional_int("PITCH_MAX_COUNT")
    
    # Web UI server configuration
    web_host: str = os.getenv("WEB_HOST", "0.0.0.0")
    web_port: int = int(os.getenv("WEB_PORT", "5050"))


CONFIG = TrackerConfig()
