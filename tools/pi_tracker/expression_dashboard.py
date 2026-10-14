"""Read-only Pi expression dashboard; it never connects to Operator or commands Bingo."""
from __future__ import annotations

import argparse
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse

from detector import PersonDetector


@dataclass
class Tuning:
    roi_x: float = 0.0
    roi_y: float = 0.0
    roi_w: float = 1.0
    roi_h: float = 1.0
    person_confidence: float = 0.35
    expression_confidence: float = 0.60
    smoothing_alpha: float = 0.35

    def validate(self) -> None:
        if not all(0.0 <= value <= 1.0 for value in asdict(self).values()):
            raise ValueError("all tuning values must be in [0, 1]")
        if self.roi_w <= 0 or self.roi_h <= 0 or self.roi_x + self.roi_w > 1 or self.roi_y + self.roi_h > 1:
            raise ValueError("ROI must be a non-empty rectangle inside the image")


class ExpressionEngine:
    labels = ("neutral", "happiness", "surprise", "sadness", "anger", "disgust", "fear", "contempt")

    def __init__(self, model: Path, cascade: Path) -> None:
        options = ort.SessionOptions()
        options.intra_op_num_threads = 4
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(str(model), sess_options=options, providers=["CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name
        self.cascade = cv2.CascadeClassifier(str(cascade))
        if self.cascade.empty():
            raise RuntimeError(f"cannot load Haar cascade: {cascade}")
        self.smoothed: dict[str, float] | None = None

    def evaluate(self, frame: np.ndarray, person_box: tuple[int, int, int, int] | None, alpha: float) -> dict:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        # This is deliberately more permissive than the expression-quality
        # threshold: retain a distant face box for diagnostics, then return
        # uncertain below rather than inventing a smile/frown.
        faces = self.cascade.detectMultiScale(gray, scaleFactor=1.12, minNeighbors=4, minSize=(24, 24))
        candidates = [(int(x), int(y), int(x + w), int(y + h)) for x, y, w, h in faces]
        if person_box:
            px1, py1, px2, py2 = person_box
            candidates = [box for box in candidates if px1 <= (box[0] + box[2]) / 2 <= px2 and py1 <= (box[1] + box[3]) / 2 <= py2]
        if not candidates:
            self.smoothed = None
            return {"available": True, "face": None, "label": "uncertain", "confidence": 0.0, "scores": {}}
        face = max(candidates, key=lambda box: (box[2] - box[0]) * (box[3] - box[1]))
        x1, y1, x2, y2 = face
        if min(x2 - x1, y2 - y1) < 32:
            self.smoothed = None
            return {"available": True, "face": face, "label": "uncertain", "confidence": 0.0, "scores": {}}
        crop = cv2.resize(gray[y1:y2, x1:x2], (64, 64), interpolation=cv2.INTER_AREA).astype(np.float32)[None, None]
        logits = np.asarray(self.session.run(None, {self.input_name: crop})[0], dtype=np.float32).reshape(-1)
        probs = np.exp(logits - logits.max()); probs /= probs.sum()
        scores = dict(zip(self.labels, map(float, probs), strict=True))
        self.smoothed = scores if self.smoothed is None else {key: alpha * value + (1 - alpha) * self.smoothed[key] for key, value in scores.items()}
        smile = self.smoothed["happiness"]
        frown = max(self.smoothed["anger"], self.smoothed["sadness"], self.smoothed["disgust"])
        neutral = self.smoothed["neutral"]
        label, confidence = max((("smile", smile), ("frown", frown), ("neutral", neutral)), key=lambda item: item[1])
        return {"available": True, "face": face, "label": label, "confidence": confidence, "scores": {"smile": smile, "frown": frown, "neutral": neutral}}


def main() -> None:
    parser = argparse.ArgumentParser(description="TALOS read-only expression dashboard")
    parser.add_argument("--camera", default="rtsp://localhost:8554/camera")
    parser.add_argument("--person-model", default="yolo26n.onnx")
    parser.add_argument("--expression-model", type=Path, required=True)
    parser.add_argument("--cascade", type=Path, required=True)
    parser.add_argument("--port", type=int, default=5051)
    args = parser.parse_args()
    tuning, lock, latest = Tuning(), threading.Lock(), {"frame": None, "status": {"state": "starting"}}
    detector = PersonDetector(args.person_model, conf_thresh=tuning.person_confidence, infer_size=(320, 320), allow_fallback=False)
    expression = ExpressionEngine(args.expression_model, args.cascade)

    def worker() -> None:
        cap = cv2.VideoCapture(args.camera, cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        while True:
            ok, frame = cap.read()
            if not ok:
                time.sleep(1); cap.release(); cap = cv2.VideoCapture(args.camera, cv2.CAP_FFMPEG); continue
            with lock: current = Tuning(**asdict(tuning))
            h, w = frame.shape[:2]; x, y, rw, rh = int(w*current.roi_x), int(h*current.roi_y), int(w*current.roi_w), int(h*current.roi_h)
            roi = frame[y:y+rh, x:x+rw]; detector.conf_thresh = current.person_confidence
            people = detector.detect(roi)
            person = max(people, key=lambda item: item.confidence).box if people else None
            if person: person = (person[0]+x, person[1]+y, person[2]+x, person[3]+y)
            status = expression.evaluate(frame, person, current.smoothing_alpha)
            status.update({"state": "ready", "person": person, "person_confidence": max((item.confidence for item in people), default=0.0), "roi": [current.roi_x,current.roi_y,current.roi_w,current.roi_h]})
            canvas = frame.copy(); cv2.rectangle(canvas,(x,y),(x+rw,y+rh),(255,180,0),2)
            if person: cv2.rectangle(canvas, person[:2], person[2:], (0,255,0), 2)
            if status["face"]: cv2.rectangle(canvas, status["face"][:2], status["face"][2:], (255,0,255), 2)
            cv2.putText(canvas, f"{status['label']} {status['confidence']:.2f}", (10,30), cv2.FONT_HERSHEY_SIMPLEX, .8, (0,255,255),2)
            with lock: latest.update(frame=canvas, status=status)

    threading.Thread(target=worker, daemon=True, name="ExpressionDashboard").start()
    app = FastAPI(title="TALOS Expression Dashboard")
    @app.get("/api/status")
    def status():
        with lock: return {"tuning": asdict(tuning), **latest["status"], "physical_commands": False}
    @app.post("/api/tuning")
    def update(payload: dict):
        with lock:
            candidate = Tuning(**{**asdict(tuning), **payload})
            try: candidate.validate()
            except (TypeError, ValueError) as exc: raise HTTPException(422, str(exc)) from exc
            tuning.__dict__.update(asdict(candidate))
            return asdict(tuning)
    @app.get("/video_feed")
    def video():
        def feed():
            while True:
                with lock: frame = latest["frame"]
                if frame is not None:
                    _, jpeg = cv2.imencode(".jpg", frame)
                    yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg.tobytes() + b"\r\n"
                time.sleep(.1)
        return StreamingResponse(feed(), media_type="multipart/x-mixed-replace; boundary=frame")
    @app.get("/", response_class=HTMLResponse)
    def ui(): return HTMLResponse('''<html><body style="background:#111;color:#ddd;font-family:sans-serif"><h1>TALOS Expression (read-only)</h1><p>No Operator connection; no physical commands.</p><img src="/video_feed" style="max-width:70vw"><pre id="s"></pre><h3>ROI / Detector tuning</h3><input id="x" placeholder="roi_x"><input id="y" placeholder="roi_y"><input id="w" placeholder="roi_w"><input id="h" placeholder="roi_h"><input id="c" placeholder="person confidence"><input id="a" placeholder="smoothing alpha"><button onclick="save()">Apply</button><script>async function tick(){let d=await (await fetch('/api/status')).json();s.textContent=JSON.stringify(d,null,2);[x,y,w,h,c,a].forEach((e,i)=>e.value=[d.tuning.roi_x,d.tuning.roi_y,d.tuning.roi_w,d.tuning.roi_h,d.tuning.person_confidence,d.tuning.smoothing_alpha][i]);}async function save(){await fetch('/api/tuning',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({roi_x:+x.value,roi_y:+y.value,roi_w:+w.value,roi_h:+h.value,person_confidence:+c.value,smoothing_alpha:+a.value})});}setInterval(tick,500);tick();</script></body></html>''')
    uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="warning")

if __name__ == "__main__": main()
