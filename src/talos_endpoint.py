import os
import threading
from contextlib import asynccontextmanager
from dataclasses import dataclass

import uvicorn
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from loguru import logger

from src.talos_app import App as TalosApp

from .connection.connection import ConnectionCollection


@asynccontextmanager
async def lifespan(app: FastAPI):
    if _talos_app_instance is None:
        logger.error("Talos app instance is not initialized")
        yield
        return
    # Don't auto-start stream on startup - wait for a connection to be opened
    logger.info("Talos endpoint started. Waiting for camera connection...")
    try:
        yield
    finally:
        _talos_app_instance.stop_stream()


app = FastAPI(lifespan=lifespan)
_talos_app_instance: TalosApp | None = None
"""
Global variable to hold the Talos app instance
This must be readonly after initialization for thread safety
"""

MEDIAMTX_BASE_URL = os.getenv("MEDIAMTX_BASE_URL", "http://localhost:8888")
MEDIAMTX_STREAM_PATH = os.getenv("MEDIAMTX_STREAM_PATH", "stream")
MEDIAMTX_RTSP_URL = os.getenv("MEDIAMTX_RTSP_URL", "rtsp://localhost:8554/stream")
MEDIAMTX_USE_DOCKER = os.getenv("MEDIAMTX_USE_DOCKER", "false").lower() in {
    "1",
    "true",
    "yes",
}
MEDIAMTX_DOCKER_NETWORK = os.getenv("MEDIAMTX_DOCKER_NETWORK", "mediamtx_net")
MEDIAMTX_FPS = os.getenv("MEDIAMTX_FPS")


@dataclass(frozen=True)
class Context:
    talos_app: TalosApp
    connections: ConnectionCollection


async def ctx():
    if _talos_app_instance is None:
        logger.error("Talos app instance is not initialized")
        raise RuntimeError("Talos app instance is not initialized")
    return Context(
        talos_app=_talos_app_instance, connections=_talos_app_instance.connections
    )


def _ensure_stream_started(talos_app: TalosApp) -> None:
    logger.debug(
        f"_ensure_stream_started called: is_streaming={talos_app.is_streaming()}"
    )
    if talos_app.is_streaming():
        logger.debug("Stream already running, skipping start")
        return

    # Check App's active connection first, then fallback to tracker's active connection
    active_conn = talos_app.connections.get_active()
    if active_conn is None:
        logger.warning("Cannot start stream: No active camera connection")
        return

    logger.info(f"Calling start_stream for {active_conn.host}")
    talos_app.start_stream(
        output_url=MEDIAMTX_RTSP_URL,
        hostname=active_conn.host,
        fps=int(MEDIAMTX_FPS) if MEDIAMTX_FPS else None,
        use_docker=MEDIAMTX_USE_DOCKER,
        docker_network=MEDIAMTX_DOCKER_NETWORK if MEDIAMTX_USE_DOCKER else None,
    )
    logger.debug(f"After start_stream: is_streaming={talos_app.is_streaming()}")


@app.get("/")
async def root(context: Context = Depends(ctx)):
    active_host = context.talos_app.get_active_hostname()

    logger.debug(
        f"Root endpoint: active_hostname={active_host}, connections={list(context.talos_app.connections.keys())}"
    )

    if active_host is None:
        logger.warning("No active connection found, returning 503")
        raise HTTPException(
            status_code=503,
            detail="No active camera connection. Please open a connection first through the GUI/TUI.",
        )

    logger.debug("Calling _ensure_stream_started")
    _ensure_stream_started(context.talos_app)

    logger.debug(
        f"After _ensure_stream_started: is_streaming={context.talos_app.is_streaming()}"
    )
    if not context.talos_app.is_streaming():
        logger.error("Stream failed to start, returning 503")
        raise HTTPException(
            status_code=503,
            detail="Failed to start stream. Check logs for details.",
        )

    hls_url = f"{MEDIAMTX_BASE_URL.rstrip('/')}/{MEDIAMTX_STREAM_PATH}/"
    logger.info(f"Redirecting to HLS viewer: {hls_url}")
    return RedirectResponse(hls_url)


@app.get("/health")
async def health():
    if _talos_app_instance is None:
        return {"status": "uninitialized"}
    return {"status": "ok"}


@app.get("/status")
async def status(context: Context = Depends(ctx)):
    """Get detailed status of the application and connections."""
    return {
        "active_hostname": context.talos_app.get_active_hostname(),
        "connections": list(context.talos_app.connections.keys()),
        "is_streaming": context.talos_app.is_streaming(),
        "tracker_active_connection": conn.host
        if (conn := context.connections.get_active()) is not None
        else None,
    }


@app.post("/stream/start")
async def start_stream(data: dict, context: Context = Depends(ctx)):
    """
    Start an ffmpeg stream from the active (or specified) connection.

    Request: {
        "output_url": "rtsp://localhost:8554/stream",
        "hostname": "optional-hostname",
        "fps": 30,
        "use_docker": false,
        "docker_image": "jrottenberg/ffmpeg:6.1-alpine",
        "docker_network": "mediamtx_net"
    }
    """
    output_url = data.get("output_url")
    if not output_url:
        raise HTTPException(status_code=400, detail="Missing output_url")

    context.talos_app.start_stream(
        output_url=output_url,
        hostname=data.get("hostname"),
        fps=data.get("fps"),
        use_docker=bool(data.get("use_docker", False)),
        docker_image=data.get("docker_image"),
        docker_network=data.get("docker_network"),
    )

    return {"status": "started", "output_url": output_url}


@app.post("/stream/stop")
async def stop_stream(context: Context = Depends(ctx)):
    """Stop an active ffmpeg stream if one is running."""
    context.talos_app.stop_stream()
    return {"status": "stopped"}


class TalosEndpoint:
    thread: threading.Thread

    def __init__(self, talos_app: TalosApp):
        global _talos_app_instance
        _talos_app_instance = talos_app

    def run(self, host="0.0.0.0", port=8000):
        """Run the FastAPI application using Uvicorn in a separate thread."""
        self.thread = threading.Thread(
            target=self._run_uvicorn, args=(host, port), daemon=True
        )
        self.thread.start()
        return self.thread

    def _run_uvicorn(self, host: str, port: int):
        uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
