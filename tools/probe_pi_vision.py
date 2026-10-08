"""Read-only live video/perception probe; never constructs a robot Publisher."""
import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2
import numpy as np
from src.connection.connection import VideoConnection
from src.interface.web.server import encode_jpeg
from src.tracking.pi_vision import request_json, validate_observations

parser = argparse.ArgumentParser()
parser.add_argument("--host", default="bluey.local")
parser.add_argument("--port", type=int, default=5051)
parser.add_argument("--seconds", type=float, default=8)
args = parser.parse_args()
video = VideoConnection(f"rtsp://{args.host}:8554/camera", background_capture=True)
sequences, detections, ages, inference = set(), set(), [], []
start = time.monotonic()
first_capture_sequence = None
try:
    while time.monotonic() - start < args.seconds:
        packet = video.get_latest_packet()
        if packet:
            sequences.add(packet.frame_sequence)
            if first_capture_sequence is None:
                first_capture_sequence = packet.frame_sequence
        try:
            sample = validate_observations(request_json(f"http://{args.host}:{args.port}/api/v1/observations"))
            if sample["sequence"] not in detections:
                detections.add(sample["sequence"])
                ages.append(sample["age_s"])
                inference.append(sample["inference_s"])
        except ValueError:
            pass
        time.sleep(0.04)
    packet = video.get_latest_packet()
    elapsed = time.monotonic() - start
    image = cv2.imdecode(np.frombuffer(encode_jpeg(packet.image), dtype=np.uint8), cv2.IMREAD_COLOR)
    print(json.dumps({"rtsp_shape": packet.image.shape, "commander_jpeg_shape": image.shape,
                      "decoded_fps": round((packet.frame_sequence - first_capture_sequence) / elapsed, 1),
                      "observation_fps": round(len(detections) / elapsed, 1),
                      "inference_median_ms": round(float(np.median(inference)) * 1000, 1),
                      "observation_age_median_ms": round(float(np.median(ages)) * 1000, 1),
                      "observation_age_p95_ms": round(float(np.percentile(ages, 95)) * 1000, 1)}))
finally:
    video.close()
