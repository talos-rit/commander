"""Local, opt-in face re-identification. No selected identity means no target."""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort


class IdentityLibrary:
    def __init__(self, model_path: str, cascade_path: str, library_path: str, threshold: float = 0.42) -> None:
        self.path, self.threshold = Path(library_path), threshold
        self.cascade = cv2.CascadeClassifier(cascade_path)
        self.session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name
        self.items: dict[str, list[float]] = json.loads(self.path.read_text()) if self.path.exists() else {}
        self.selected: str | None = None
        self.allow_anyone = False
        self.last_face: tuple[int, int, int, int] | None = None
        self.candidates: list[tuple[int, int, int, int]] = []

    def names(self) -> list[str]: return sorted(self.items)
    def select(self, name: str | None) -> None:
        if name is not None and name not in self.items: raise KeyError(name)
        self.selected = name
    def enroll(self, name: str, frame: np.ndarray) -> None:
        embedding = self._embedding_for_largest_face(frame)
        if embedding is None: raise ValueError("no usable face in current frame")
        self.items[name] = embedding.tolist(); self.path.parent.mkdir(parents=True, exist_ok=True); self.path.write_text(json.dumps(self.items))
    def remove(self, name: str) -> None:
        self.items.pop(name, None)
        if self.selected == name: self.selected = None
        self.path.write_text(json.dumps(self.items))
    def filter(self, frame: np.ndarray, detections):
        if self.allow_anyone: return detections
        if self.selected is None: return []
        reference = np.asarray(self.items[self.selected], np.float32)
        best, best_score, best_face = None, -1.0, None
        for det in detections:
            face = self._face_in_box(frame, det.box)
            if face is None: continue
            vector = self._embed(frame, face)
            score = float(np.dot(reference, vector))
            if score > best_score: best, best_score, best_face = det, score, face
        self.last_face = best_face
        return [best] if best is not None and best_score >= self.threshold else []
    def scan(self, frame: np.ndarray) -> None:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        # Acquisition may start with a small distant face.  Embeddings from it
        # are naturally less certain, but rejecting it outright made the
        # library appear empty until a person walked very close to the camera.
        faces = self.cascade.detectMultiScale(gray, 1.12, 4, minSize=(32, 32))
        raw = [(int(x), int(y), int(x+w), int(y+h)) for x,y,w,h in faces]
        # Keep only spatially distinct candidates; Haar often emits near duplicates.
        kept: list[tuple[int,int,int,int]] = []
        for box in sorted(raw, key=lambda item:(item[2]-item[0])*(item[3]-item[1]), reverse=True):
            cx, cy = (box[0]+box[2])/2, (box[1]+box[3])/2
            if all((cx-(old[0]+old[2])/2)**2 + (cy-(old[1]+old[3])/2)**2 > 50**2 for old in kept): kept.append(box)
        self.candidates = kept[:8]
    def crop(self, frame: np.ndarray, index: int) -> np.ndarray:
        x1,y1,x2,y2 = self.candidates[index]
        return frame[max(0,y1):y2, max(0,x1):x2].copy()
    def status(self) -> dict:
        return {"identities": self.names(), "selected": self.selected, "allow_anyone": self.allow_anyone, "threshold": self.threshold, "face": self.last_face, "candidates": self.candidates}
    def _embedding_for_largest_face(self, frame):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY); faces = self.cascade.detectMultiScale(gray, 1.12, 4, minSize=(32,32))
        if len(faces) == 0: return None
        x,y,w,h = max(faces, key=lambda item:item[2]*item[3]); return self._embed(frame,(int(x),int(y),int(x+w),int(y+h)))
    def _face_in_box(self, frame, box):
        x1,y1,x2,y2 = box; gray=cv2.cvtColor(frame[y1:y2,x1:x2],cv2.COLOR_BGR2GRAY)
        faces=self.cascade.detectMultiScale(gray,1.12,4,minSize=(32,32))
        if len(faces)==0:return None
        x,y,w,h=max(faces,key=lambda item:item[2]*item[3]); return (x1+int(x),y1+int(y),x1+int(x+w),y1+int(y+h))
    def _embed(self, frame, face):
        x1,y1,x2,y2=face; crop=cv2.resize(frame[y1:y2,x1:x2],(112,112)); rgb=cv2.cvtColor(crop,cv2.COLOR_BGR2RGB)
        tensor=(np.transpose(rgb,(2,0,1)).astype(np.float32)-127.5)/128.0
        vector=np.asarray(self.session.run(None,{self.input_name:tensor[None]})[0],np.float32).reshape(-1)
        return vector/max(float(np.linalg.norm(vector)),1e-9)
