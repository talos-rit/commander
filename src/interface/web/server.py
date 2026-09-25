import asyncio
import os
import threading
from pathlib import Path
from typing import Any, Literal

import cv2
import numpy as np
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .backend import BackendError, CommanderWebBackend

WEB_DIST_DIR = Path(__file__).resolve().parents[3] / "web" / "dist"
MJPEG_BOUNDARY = "frame"
JPEG_QUALITY = 80


class ViewRequest(BaseModel):
    display_mode: Literal["one_screen", "two_screen"] | None = None
    one_screen_mode: Literal["dynamic", "manual"] | None = None
    ui_mode: Literal["simple", "debug"] | None = None


class SlotsRequest(BaseModel):
    camera_1: str | None = None
    camera_2: str | None = None


class SelectRequest(BaseModel):
    host: str | None = None
    slot: Literal[1, 2] | None = None


class TargetRequest(BaseModel):
    host: str | None = None


class AutoTrackRequest(BaseModel):
    enabled: bool
    host: str | None = None


class MoveRequest(BaseModel):
    direction: Literal["up", "down", "left", "right"]


class JogModeRequest(BaseModel):
    mode: Literal["discrete", "continuous"]


class ModelRequest(BaseModel):
    model: str | None = None


def encode_jpeg(frame: np.ndarray, max_width: int | None = None) -> bytes | None:
    if max_width is not None and frame.shape[1] > max_width:
        height = int(frame.shape[0] * max_width / frame.shape[1])
        frame = cv2.resize(frame, (max_width, height), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    return buf.tobytes() if ok else None


def create_web_app(
    backend: CommanderWebBackend, static_dir: Path | None = WEB_DIST_DIR
) -> FastAPI:
    app = FastAPI(title="Commander")
    # Set when the server starts shutting down so open MJPEG streams end instead
    # of holding the process open.
    app.state.streams_stopping = threading.Event()
    api = APIRouter(prefix="/api")

    @app.exception_handler(BackendError)
    async def backend_error_handler(_request: Request, exc: BackendError):
        return JSONResponse(status_code=exc.status, content={"detail": str(exc)})

    # Refuse (rather than queue) API calls until startup has opened the
    # connections, so nothing acts on or persists a half-initialized state.
    @app.middleware("http")
    async def wait_for_startup(request: Request, call_next):
        path = request.url.path
        if path.startswith("/api/") and path != "/api/health" and not backend.ready:
            return JSONResponse(
                status_code=503,
                content={"detail": "Commander is connecting to cameras…", "starting": True},
            )
        return await call_next(request)

    @api.get("/health")
    def health():
        return {"status": "ok", "ready": backend.ready}

    @api.get("/status")
    def status():
        return backend.status()

    @api.post("/view")
    def set_view(req: ViewRequest):
        backend.set_view(req.display_mode, req.one_screen_mode, req.ui_mode)
        return backend.status()

    @api.post("/cameras/slots")
    def assign_slots(req: SlotsRequest):
        backend.assign_slots(req.camera_1, req.camera_2)
        return backend.status()

    @api.post("/cameras/select")
    def select(req: SelectRequest):
        backend.select(host=req.host, slot=req.slot)
        return backend.status()

    @api.post("/control/home")
    def home(req: TargetRequest | None = None):
        target = backend.home(req.host if req else None)
        return {"host": target}

    @api.post("/control/auto-track")
    def auto_track(req: AutoTrackRequest):
        enabled = backend.set_auto_track(req.enabled, req.host)
        return {"enabled": enabled}

    @api.post("/control/move/start")
    def move_start(req: MoveRequest):
        backend.move(req.direction, active=True)
        return {"ok": True}

    @api.post("/control/move/stop")
    def move_stop(req: MoveRequest):
        backend.move(req.direction, active=False)
        return {"ok": True}

    @api.post("/control/jog-mode")
    def jog_mode(req: JogModeRequest):
        return {"mode": backend.set_jog_mode(req.mode)}

    @api.post("/control/model")
    def model(req: ModelRequest):
        return {"model": backend.set_model(req.model)}

    @api.get("/cameras/{host}/snapshot")
    def snapshot(host: str, width: int | None = None):
        frame = backend.get_frame(host)
        if frame is None:
            raise HTTPException(status_code=503, detail=f"No frame from {host}")
        data = encode_jpeg(frame, width)
        if data is None:
            raise HTTPException(status_code=500, detail="JPEG encoding failed")
        return Response(content=data, media_type="image/jpeg", headers={"Cache-Control": "no-store"})

    @api.get("/cameras/{host}/mjpeg")
    async def mjpeg(
        host: str, request: Request, width: int | None = None, frames: int | None = None
    ):
        interval = 1.0 / max(1, backend.frame_fps(host))

        async def stream():
            last_sequence = None
            sent = 0
            # Each part is terminated by the next boundary so browsers render it
            # immediately instead of waiting for another frame (e.g. a paused feed).
            yield f"--{MJPEG_BOUNDARY}\r\n".encode()
            stopping = app.state.streams_stopping
            while not stopping.is_set() and not await request.is_disconnected():
                if frames is not None and sent >= frames:
                    return
                sequence = backend.frame_sequence(host)
                frame = backend.get_frame(host) if sequence != last_sequence else None
                if frame is None:
                    await asyncio.sleep(interval)
                    continue
                last_sequence = sequence
                data = await asyncio.to_thread(encode_jpeg, frame, width)
                if data is not None:
                    sent += 1
                    yield (
                        f"Content-Type: image/jpeg\r\nContent-Length: {len(data)}\r\n\r\n".encode()
                        + data
                        + f"\r\n--{MJPEG_BOUNDARY}\r\n".encode()
                    )
                await asyncio.sleep(interval)

        return StreamingResponse(
            stream(),
            media_type=f"multipart/x-mixed-replace; boundary={MJPEG_BOUNDARY}",
            headers={"Cache-Control": "no-store"},
        )

    @api.get("/settings")
    def get_settings():
        return backend.get_settings()

    @api.put("/settings")
    def put_settings(updates: dict[str, Any]):
        return backend.update_settings(updates)

    @api.get("/robots")
    def list_robots():
        return backend.list_robots()

    @api.post("/robots", status_code=201)
    def add_robot(data: dict[str, Any]):
        return backend.add_robot(data)

    @api.put("/robots/{host}")
    def update_robot(host: str, data: dict[str, Any]):
        return backend.update_robot(host, data)

    @api.delete("/robots/{host}", status_code=204)
    def delete_robot(host: str):
        backend.delete_robot(host)
        return Response(status_code=204)

    app.include_router(api)

    if static_dir is not None and static_dir.is_dir():
        index = static_dir / "index.html"
        assets = static_dir / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            candidate = (static_dir / path).resolve()
            if path and candidate.is_file() and static_dir.resolve() in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(index)
    else:

        @app.get("/", include_in_schema=False)
        def no_frontend():
            return JSONResponse(
                {
                    "detail": "Web UI is not built. Run `pnpm --dir web build`, "
                    "or use the Vite dev server (`pnpm --dir web dev`)."
                },
                status_code=503,
            )

    return app


def web_dist_available() -> bool:
    return (WEB_DIST_DIR / "index.html").is_file() and os.access(WEB_DIST_DIR, os.R_OK)
