"""
Detector module for Pi Edge Tracker.
ONNX is the production backend. Alternate detectors require an explicit opt-in and
are never silently made eligible for autonomous motion.
"""

from dataclasses import dataclass
from os import path
from typing import List, Optional, Tuple
import cv2
import numpy as np
from loguru import logger


@dataclass
class Detection:
    box: Tuple[int, int, int, int]  # (x1, y1, x2, y2) in original frame coords
    confidence: float
    class_id: int
    class_name: str
    aim_point: Optional[Tuple[int, int]] = None
    keypoints: Optional[Tuple[Tuple[int, int, float], ...]] = None

    @property
    def center(self) -> Tuple[int, int]:
        """Returns a pose-derived torso aim point when available."""
        if self.aim_point is not None:
            return self.aim_point
        x1, y1, x2, y2 = self.box
        h = max(1, y2 - y1)
        head_y = int(y1 + 0.18 * h)
        return int((x1 + x2) / 2), head_y

    @property
    def full_body_center(self) -> Tuple[int, int]:
        x1, y1, x2, y2 = self.box
        return int((x1 + x2) / 2), int((y1 + y2) / 2)

    @property
    def width(self) -> int:
        return self.box[2] - self.box[0]

    @property
    def height(self) -> int:
        return self.box[3] - self.box[1]


class PersonDetector:
    """Detects people in camera frames using ONNX Runtime, Ultralytics YOLO, or OpenCV HOG."""

    def __init__(
        self,
        model_weights: str = "yolo26n.onnx",
        conf_thresh: float = 0.45,
        infer_size: Tuple[int, int] = (320, 320),
        allow_fallback: bool = False,
    ):
        self.conf_thresh = conf_thresh
        self.infer_size = infer_size
        self.model_weights = model_weights
        self.backend = "unknown"
        self.session = None
        self.input_name = None
        self.allow_fallback = allow_fallback
        self.healthy = False
        self.last_error: Optional[str] = None

        self._initialize_detector()

    def _initialize_detector(self):
        # 1. Try ONNX Runtime (fastest on Pi 4 CPU with ARM NEON)
        onnx_candidates = [
            self.model_weights,
            path.splitext(self.model_weights)[0] + ".onnx",
            "yolo26n.onnx",
            path.join(path.dirname(__file__), "yolo26n.onnx")
        ]

        found_onnx = None
        for candidate in onnx_candidates:
            if candidate and path.exists(candidate):
                found_onnx = candidate
                break

        if found_onnx:
            try:
                import onnxruntime as ort
                logger.info(f"[Detector] Loading ONNX model '{found_onnx}' with ONNX Runtime...")
                opts = ort.SessionOptions()
                opts.intra_op_num_threads = 4
                opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
                opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
                self.session = ort.InferenceSession(found_onnx, sess_options=opts, providers=["CPUExecutionProvider"])
                self.input_name = self.session.get_inputs()[0].name
                in_shape = self.session.get_inputs()[0].shape
                if len(in_shape) == 4 and isinstance(in_shape[2], int) and isinstance(in_shape[3], int):
                    self.infer_size = (in_shape[3], in_shape[2])
                self.backend = "onnxruntime"
                self.healthy = True
                logger.info(f"[Detector] ONNX Runtime initialized ({found_onnx}), input size: {self.infer_size}.")
                return
            except Exception as e:
                self.last_error = str(e)
                logger.error(f"[Detector] Failed to load ONNX model via onnxruntime: {e}")

        if not self.allow_fallback:
            model_reason = self.last_error or f"ONNX model not found: {self.model_weights}"
            raise RuntimeError(f"Production detector unavailable; refusing autonomous fallback ({model_reason})")

        # 2. Try Ultralytics YOLO
        try:
            from ultralytics import YOLO
            logger.info(f"[Detector] Loading YOLO model '{self.model_weights}' via Ultralytics...")
            self.session = YOLO(self.model_weights)
            self.backend = "ultralytics_yolo"
            self.healthy = True
            logger.info(f"[Detector] Ultralytics YOLO loaded successfully ({self.model_weights}).")
            return
        except Exception:
            logger.warning("[Detector] Ultralytics not available or model missing.")

        # 3. Fallback to OpenCV HOG Person Detector
        try:
            hog = cv2.HOGDescriptor()
            hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
            self.session = hog
            self.backend = "opencv_hog"
            self.healthy = True
            logger.info("[Detector] Fallback: OpenCV HOG Person Detector initialized.")
        except Exception as e:
            logger.error(f"[Detector] Failed to initialize OpenCV HOG: {e}")
            self.backend = "dummy"
            self.last_error = str(e)
            raise RuntimeError(f"No usable person detector: {e}") from e

    def detect(self, frame: np.ndarray) -> List[Detection]:
        """Detects people in the frame and returns bounding boxes mapped to the original frame size."""
        if frame is None or frame.size == 0:
            return []

        orig_h, orig_w = frame.shape[:2]
        infer_w, infer_h = self.infer_size
        detections: List[Detection] = []

        if self.backend == "onnxruntime":
            try:
                # Resize and normalize to (1, 3, 320, 320) RGB float32
                resized = cv2.resize(frame, (infer_w, infer_h), interpolation=cv2.INTER_LINEAR)
                rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
                input_tensor = np.transpose(rgb, (2, 0, 1)).astype(np.float32) / 255.0
                input_tensor = np.expand_dims(input_tensor, axis=0)

                output = self.session.run(None, {self.input_name: input_tensor})[0]
                detections.extend(self._decode_onnx_output(output, orig_w, orig_h))
            except Exception as e:
                logger.error(f"[Detector] ONNX inference error: {e}")
                self.healthy = False
                self.last_error = str(e)
                raise RuntimeError(f"ONNX inference failed: {e}") from e

        elif self.backend == "ultralytics_yolo":
            try:
                resized = cv2.resize(frame, (infer_w, infer_h), interpolation=cv2.INTER_LINEAR)
                scale_x = orig_w / float(infer_w)
                scale_y = orig_h / float(infer_h)
                results = self.session.predict(
                    source=resized,
                    classes=[0],
                    conf=self.conf_thresh,
                    verbose=False,
                    device="cpu"
                )
                if results and len(results) > 0 and results[0].boxes is not None:
                    boxes = results[0].boxes
                    for i in range(len(boxes)):
                        xyxy = boxes.xyxy[i].cpu().numpy()
                        conf = float(boxes.conf[i].cpu().numpy())
                        cls_id = int(boxes.cls[i].cpu().numpy())
                        x1 = int(xyxy[0] * scale_x)
                        y1 = int(xyxy[1] * scale_y)
                        x2 = int(xyxy[2] * scale_x)
                        y2 = int(xyxy[3] * scale_y)
                        detections.append(Detection(
                            box=(x1, y1, x2, y2),
                            confidence=conf,
                            class_id=cls_id,
                            class_name="person"
                        ))
            except Exception as e:
                logger.error(f"[Detector] YOLO inference error: {e}")
                self.healthy = False
                self.last_error = str(e)
                raise RuntimeError(f"YOLO inference failed: {e}") from e

        elif self.backend == "opencv_hog":
            try:
                resized = cv2.resize(frame, (infer_w, infer_h), interpolation=cv2.INTER_LINEAR)
                scale_x = orig_w / float(infer_w)
                scale_y = orig_h / float(infer_h)
                boxes, weights = self.session.detectMultiScale(
                    resized,
                    winStride=(8, 8),
                    padding=(4, 4),
                    scale=1.05
                )
                for (x, y, w, h), conf in zip(boxes, weights):
                    if conf >= 0.2:
                        x1 = int(x * scale_x)
                        y1 = int(y * scale_y)
                        x2 = int((x + w) * scale_x)
                        y2 = int((y + h) * scale_y)
                        detections.append(Detection(
                            box=(x1, y1, x2, y2),
                            confidence=float(conf),
                            class_id=0,
                            class_name="person"
                        ))
            except Exception as e:
                logger.error(f"[Detector] HOG detection error: {e}")
                self.healthy = False
                self.last_error = str(e)
                raise RuntimeError(f"HOG inference failed: {e}") from e

        # Sort detections by area (closest person first)
        detections.sort(key=lambda d: d.width * d.height, reverse=True)
        return detections

    def _decode_onnx_output(self, output: np.ndarray, orig_w: int, orig_h: int) -> List[Detection]:
        """Decode either end-to-end ``N x 6`` or raw Ultralytics ``C x N`` output."""
        predictions = np.asarray(output)
        if predictions.ndim == 3 and predictions.shape[0] == 1:
            predictions = predictions[0]
        if predictions.ndim != 2:
            raise ValueError(f"unsupported ONNX output shape: {predictions.shape}")

        infer_w, infer_h = self.infer_size
        scale_x = orig_w / float(infer_w)
        scale_y = orig_h / float(infer_h)
        candidates: List[Tuple[Tuple[float, float, float, float], float]] = []

        if predictions.shape[1] == 6:
            # Export with integrated NMS: x1, y1, x2, y2, confidence, class.
            for pred in predictions:
                if float(pred[4]) >= self.conf_thresh and int(pred[5]) == 0:
                    candidates.append(((float(pred[0]), float(pred[1]), float(pred[2]), float(pred[3])), float(pred[4])))
        else:
            # Standard Ultralytics export: (4 + classes, anchors), center-width boxes.
            if predictions.shape[1] < 5 or (predictions.shape[0] <= 256 and predictions.shape[1] > predictions.shape[0]):
                predictions = predictions.T
            if predictions.shape[1] < 5:
                raise ValueError(f"unsupported raw ONNX output shape: {predictions.shape}")
            for pred in predictions:
                class_scores = pred[4:]
                class_id = int(np.argmax(class_scores))
                score = float(class_scores[class_id])
                if class_id != 0 or score < self.conf_thresh:
                    continue
                center_x, center_y, width, height = (float(value) for value in pred[:4])
                candidates.append(
                    ((center_x - width / 2, center_y - height / 2, center_x + width / 2, center_y + height / 2), score)
                )

        # Some exports use normalized coordinates; most use inference-pixel coordinates.
        boxes_xywh = []
        scores = []
        boxes_xyxy = []
        for (x1, y1, x2, y2), score in candidates:
            if max(abs(x1), abs(y1), abs(x2), abs(y2)) <= 2.0:
                x1, x2 = x1 * infer_w, x2 * infer_w
                y1, y2 = y1 * infer_h, y2 * infer_h
            x1, x2 = sorted((max(0.0, min(infer_w, x1)), max(0.0, min(infer_w, x2))))
            y1, y2 = sorted((max(0.0, min(infer_h, y1)), max(0.0, min(infer_h, y2))))
            if x2 - x1 < 2 or y2 - y1 < 2:
                continue
            boxes_xyxy.append((x1, y1, x2, y2))
            boxes_xywh.append([x1, y1, x2 - x1, y2 - y1])
            scores.append(score)

        if not boxes_xywh:
            return []
        indices = cv2.dnn.NMSBoxes(boxes_xywh, scores, self.conf_thresh, 0.45)
        return [
            Detection(
                box=(
                    int(boxes_xyxy[index][0] * scale_x),
                    int(boxes_xyxy[index][1] * scale_y),
                    int(boxes_xyxy[index][2] * scale_x),
                    int(boxes_xyxy[index][3] * scale_y),
                ),
                confidence=scores[index],
                class_id=0,
                class_name="person",
            )
            for index in np.asarray(indices).reshape(-1)
        ]
