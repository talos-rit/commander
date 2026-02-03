import threading
import uuid
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import uvicorn
from aiortc import MediaStreamTrack, RTCPeerConnection, RTCSessionDescription
from aiortc.sdp import candidate_from_sdp
from av import VideoFrame
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.talos_app import App as TalosApp

app = FastAPI()
_talos_app_instance: TalosApp | None = None
"""
Global variable to hold the Talos app instance
This must be readonly after initialization for thread safety
"""


class TalosVideoTrack(MediaStreamTrack):
    """
    Custom video track that captures frames from Talos app.
    Subclasses MediaStreamTrack and provides video frames as numpy arrays.
    """

    kind = "video"

    def __init__(self, frame_getter, track_id: str):
        super().__init__()
        self.frame_getter = frame_getter
        self.track_id = track_id

    async def recv(self) -> VideoFrame:
        """
        Receive the next frame from the Talos app.
        Converts numpy arrays to av.VideoFrame for WebRTC transmission.
        """
        # Get frame from app
        frame = self.frame_getter()

        # If no frame available, return a black frame
        if frame is None:
            frame = np.zeros((480, 640, 3), dtype=np.uint8)

        # Convert frame if necessary
        if frame.ndim == 2:  # grayscale
            frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)

        # Resize if needed
        if frame.shape[0] != 480 or frame.shape[1] != 640:
            frame = cv2.resize(frame, (640, 480))

        # Ensure uint8 dtype
        frame = frame.astype(np.uint8)

        # Create VideoFrame from numpy array (BGR format for OpenCV)
        # Let aiortc handle timing - do not set pts or time_base
        video_frame = VideoFrame.from_ndarray(frame, format="bgr24")

        return video_frame


# Store peer connections for cleanup
_peer_connections: dict[str, RTCPeerConnection] = {}


@dataclass(frozen=True)
class Context:
    talos_app: TalosApp


async def ctx():
    if _talos_app_instance is None:
        raise RuntimeError("Talos app instance is not initialized")
    return Context(talos_app=_talos_app_instance)


# Templates directory
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


@app.get("/", response_class=HTMLResponse)
async def read_index(request: Request, context: Context = Depends(ctx)):
    connections = [hostname for hostname in context.talos_app.get_connections()]

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "title": "WebRTC Video Stream",
            "connections": connections,
            "active_connection": "_auto_",
        },
    )


@app.get("/app/{hostname}", response_class=HTMLResponse)
async def read_index_hostname(
    request: Request, hostname: str, context: Context = Depends(ctx)
):
    connections = [
        {"hostname": hostname} for hostname in context.talos_app.get_connections()
    ]

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "title": "WebRTC Video Stream",
            "connections": connections,
            "active_connection": hostname,
        },
    )


@app.get("/video")
async def stream_default_video(context: Context = Depends(ctx)):
    """
    WebRTC video info endpoint (for default stream).
    Actual video flows over WebRTC, not HTTP.
    """
    return {"type": "default"}


@app.get("/video/{hostname}")
async def stream_video(hostname: str, context: Context = Depends(ctx)):
    """
    WebRTC video info endpoint (for specific hostname).
    Actual video flows over WebRTC, not HTTP.
    """
    tApp = context.talos_app

    if hostname not in tApp.get_connections():
        raise HTTPException(status_code=404, detail="Hostname not found")

    return {"type": "hostname", "hostname": hostname}


@app.post("/offer")
async def handle_offer(data: dict, context: Context = Depends(ctx)):
    """
    WebRTC signaling endpoint.

    Accepts SDP offer from client, creates peer connection with video track,
    and returns SDP answer. Video media flows over WebRTC (RTP), not HTTP.

    Request: { "sdp": string, "type": "offer", "track_type": "default" | "hostname", "hostname": string }
    Response: { "sdp": string, "type": "answer", "peer_id": string }
    """
    offer_sdp: str | None = data.get("sdp")
    track_type = data.get("track_type", "default")

    if offer_sdp is None:
        raise HTTPException(status_code=400, detail="Missing SDP offer")

    # Create peer connection for this client
    pc = RTCPeerConnection()
    peer_id = str(uuid.uuid4())
    _peer_connections[peer_id] = pc

    tApp = context.talos_app

    # Create and add video track BEFORE setting remote description
    if track_type == "default":
        video_track = TalosVideoTrack(tApp.get_active_frame, peer_id)
    else:
        hostname = data.get("hostname")
        if not hostname or hostname not in tApp.get_connections():
            raise HTTPException(status_code=404, detail="Hostname not found")
        video_track = TalosVideoTrack(lambda: tApp.get_frame(hostname), peer_id)

    pc.addTransceiver(trackOrKind="video", direction="sendonly").sender.replaceTrack(
        video_track
    )

    # Set remote description (client's offer)
    offer = RTCSessionDescription(sdp=offer_sdp, type="offer")
    await pc.setRemoteDescription(offer)

    # Create and set local description (server's answer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return {
        "sdp": pc.localDescription.sdp,
        "type": pc.localDescription.type,
        "peer_id": peer_id,
    }


@app.post("/ice")
async def handle_ice(data: dict):
    """
    Handle ICE candidates from client.
    Expects: { "peer_id": string, "candidate": string, "sdpMid": string, "sdpMLineIndex": number }
    """
    peer_id = data.get("peer_id")
    candidate_str = data.get("candidate")
    sdp_mid = data.get("sdpMid")
    sdp_m_line_index = data.get("sdpMLineIndex")

    if not peer_id or peer_id not in _peer_connections:
        raise HTTPException(status_code=404, detail="Peer connection not found")

    if candidate_str:
        # Parse the candidate string and create ICE candidate with required fields
        ice_candidate = candidate_from_sdp(candidate_str)
        ice_candidate.sdpMid = sdp_mid
        ice_candidate.sdpMLineIndex = sdp_m_line_index

        await _peer_connections[peer_id].addIceCandidate(ice_candidate)

    return {"status": "ok"}


@app.delete("/offer/{peer_id}")
async def close_peer(peer_id: str):
    """
    Close a peer connection.
    Called when client disconnects or connection is no longer needed.
    """
    if peer_id in _peer_connections:
        pc = _peer_connections.pop(peer_id)
        await pc.close()
        return {"status": "closed"}

    raise HTTPException(status_code=404, detail="Peer connection not found")


@app.get("/health")
async def health():
    if _talos_app_instance is None:
        return {"status": "uninitialized"}
    return {"status": "ok"}


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

    def _run_uvicorn(self, host: str, port: int):
        uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
