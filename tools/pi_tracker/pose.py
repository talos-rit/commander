"""Offline YOLO11 pose gate for the Pi tracker.

Only COCO-person candidates with a credible torso skeleton become tracking
targets.  This rejects static false positives such as doors without using face
recognition or any network service.
"""
from __future__ import annotations

from os import path
import os
from typing import List

import cv2
import numpy as np
import onnxruntime as ort

try:
    from .detector import Detection
except ImportError:
    from detector import Detection


class PoseDetector:
    """YOLO11 COCO pose ONNX; input resolution is read from the exported model."""
    def __init__(self, model_weights: str, conf_thresh: float = 0.35, keypoint_thresh: float = 0.30) -> None:
        if not path.exists(model_weights):
            raise RuntimeError(f"pose model missing: {model_weights}")
        self.conf_thresh, self.keypoint_thresh = conf_thresh, keypoint_thresh
        options = ort.SessionOptions(); options.intra_op_num_threads = int(os.getenv("POSE_THREADS", "4"))
        options.add_session_config_entry("session.intra_op.allow_spinning", os.getenv("POSE_SPINNING", "0"))
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(model_weights, sess_options=options, providers=["CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name
        shape = self.session.get_inputs()[0].shape
        if len(shape) != 4 or shape[:2] != [1, 3] or any(not isinstance(v, int) or v <= 0 for v in shape[2:]):
            raise RuntimeError("pose model must have fixed [1,3,height,width] input; export with dynamic=False")
        self.infer_size = (int(shape[3]), int(shape[2]))
        self.healthy, self.last_error = True, None

    def detect(self, frame: np.ndarray) -> List[Detection]:
        if frame is None or frame.size == 0:
            return []
        original_h, original_w = frame.shape[:2]
        infer_w, infer_h = self.infer_size
        image = cv2.resize(frame, (infer_w, infer_h), interpolation=cv2.INTER_LINEAR)
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        tensor = np.transpose(rgb, (2, 0, 1)).astype(np.float32)[None] / 255.0
        try:
            raw = np.asarray(self.session.run(None, {self.input_name: tensor})[0], dtype=np.float32)
        except Exception as error:
            self.healthy, self.last_error = False, str(error)
            raise RuntimeError(f"pose inference failed: {error}") from error
        if raw.ndim != 3 or raw.shape[0] != 1 or raw.shape[1] != 56:
            self.healthy, self.last_error = False, "expected COCO pose output [1,56,N]"
            raise RuntimeError(self.last_error)
        rows = raw[0].T
        rows = rows[rows[:, 4] >= self.conf_thresh]  # Avoid a Python loop over thousands of rejected anchors.
        boxes, scores, candidates = [], [], []
        for row in rows:
            score = float(row[4])
            if score < self.conf_thresh:
                continue
            keypoints = row[5:].reshape(17, 3)
            aim = self._torso_aim(keypoints)
            if aim is None:
                continue
            cx, cy, bw, bh = (float(value) for value in row[:4])
            x1, y1 = max(0.0, cx - bw / 2), max(0.0, cy - bh / 2)
            x2, y2 = min(float(infer_w), cx + bw / 2), min(float(infer_h), cy + bh / 2)
            if x2 - x1 < 4 or y2 - y1 < 4:
                continue
            boxes.append([x1, y1, x2 - x1, y2 - y1]); scores.append(score)
            candidates.append((x1, y1, x2, y2, aim, score, keypoints))
        if not boxes:
            return []
        indices = np.asarray(cv2.dnn.NMSBoxes(boxes, scores, self.conf_thresh, 0.45)).reshape(-1)
        sx, sy = original_w / infer_w, original_h / infer_h
        return [
            Detection(
                (int(x1*sx), int(y1*sy), int(x2*sx), int(y2*sy)), score, 0, "pose-person",
                (int(aim[0]*sx), int(aim[1]*sy)),
                tuple((int(point[0]*sx), int(point[1]*sy), float(point[2])) for point in keypoints),
            )
            for index, (x1, y1, x2, y2, aim, score, keypoints) in ((index, candidates[index]) for index in indices)
        ]

    def _torso_aim(self, points: np.ndarray):
        # COCO: shoulders 5/6, hips 11/12. Require a pair; isolated points do
        # not make a static object a person.
        pairs = ((5, 6), (11, 12))
        valid = [(points[a], points[b]) for a, b in pairs if points[a, 2] >= self.keypoint_thresh and points[b, 2] >= self.keypoint_thresh]
        if not valid:
            return None
        a, b = valid[0]
        return ((float(a[0]) + float(b[0])) / 2, (float(a[1]) + float(b[1])) / 2)
