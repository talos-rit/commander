"""
Web server and API for Pi Edge Tracker.
Provides MJPEG annotated video feed, REST API, and a super simple Web UI showing what the Pi is doing/thinking.
"""

import time
from typing import Generator
import cv2
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse, Response

try:
    from .controller import ControllerStatus, TrackingController, TrackingState
    from .detector import PersonDetector
    from .operator_client import OperatorClient
except ImportError:
    from controller import ControllerStatus, TrackingController, TrackingState
    from detector import PersonDetector
    from operator_client import OperatorClient


def create_app(
    controller: TrackingController,
    detector: PersonDetector,
    operator: OperatorClient,
    get_latest_frame: callable,
    get_latest_status: callable,
    get_pose_tuning=None,
    update_pose_tuning=None,
    perception=None,
    standalone_control=False,
    control_lease=None,
) -> FastAPI:
    app = FastAPI(title="TALOS Pi Edge Tracker")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def draw_hud(frame: np.ndarray, status: ControllerStatus) -> np.ndarray:
        """Annotates frame with bounding box, acceptable deadband, reticles, and diagnostics."""
        canvas = frame.copy()
        h, w = canvas.shape[:2]
        cx, cy = w // 2, h // 2

        # Draw acceptable center deadband box
        left, top, right, bottom = status.acceptable_box
        deadband_color = (255, 200, 0) if status.state == TrackingState.CENTERED else (100, 100, 100)
        cv2.rectangle(canvas, (left, top), (right, bottom), deadband_color, 2)
        cv2.putText(canvas, "ACCEPTABLE REGION", (left + 5, top + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.45, deadband_color, 1)

        # Draw camera center crosshair
        cv2.drawMarker(canvas, (cx, cy), (80, 80, 80), cv2.MARKER_CROSS, 20, 1)

        # Draw detected target if present
        if status.target_box:
            x1, y1, x2, y2 = status.target_box
            tcx, tcy = status.target_center

            # Box color reflects tracking state
            if status.state == TrackingState.CENTERED:
                box_color = (0, 255, 0)  # Green when centered
            elif status.state == TrackingState.TRACKING:
                box_color = (0, 165, 255)  # Orange when tracking
            else:
                box_color = (200, 200, 200)

            cv2.rectangle(canvas, (x1, y1), (x2, y2), box_color, 2)
            if status.target_keypoints:
                points = status.target_keypoints
                for a, b in ((5,6),(5,7),(7,9),(6,8),(8,10),(5,11),(6,12),(11,12),(11,13),(13,15),(12,14),(14,16)):
                    if points[a][2] >= .30 and points[b][2] >= .30:
                        cv2.line(canvas, points[a][:2], points[b][:2], (255, 255, 0), 2)
                for x, y, confidence in points:
                    if confidence >= .30:
                        cv2.circle(canvas, (x, y), 3, (255, 255, 0), -1)
            cv2.circle(canvas, (tcx, tcy), 6, box_color, -1)

            # Error vector line pointing from camera center to target
            cv2.line(canvas, (cx, cy), (tcx, tcy), (0, 255, 255), 2)

            label = f"Target {status.target_confidence * 100:.0f}% (dX:{status.error_x}, dY:{status.error_y})"
            cv2.putText(canvas, label, (x1, max(20, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, box_color, 2)

        # Top diagnostic banner
        state_color = {
            TrackingState.TRACKING: (0, 165, 255),
            TrackingState.CENTERED: (0, 255, 0),
            TrackingState.SEARCHING: (0, 255, 255),
            TrackingState.WAITING_FEEDBACK: (0, 165, 255),
            TrackingState.DISABLED: (120, 120, 120),
            TrackingState.LIMIT_REACHED: (0, 0, 255),
            TrackingState.FAULT: (0, 0, 255),
        }.get(status.state, (255, 255, 255))

        banner_text = f"STATE: {status.state.value} | FPS: {status.fps:.1f} | CMD: {status.current_command}"
        cv2.putText(canvas, banner_text, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 3)
        cv2.putText(canvas, banner_text, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.55, state_color, 2)

        return canvas

    def mjpeg_generator() -> Generator[bytes, None, None]:
        """Generates MJPEG stream of annotated camera frames."""
        while True:
            frame = get_latest_frame()
            if frame is None:
                # Blank frame placeholder
                blank = np.zeros((240, 320, 3), dtype=np.uint8)
                cv2.putText(blank, "Waiting for Camera...", (30, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
                _, jpeg = cv2.imencode(".jpg", blank)
            else:
                status = get_latest_status()
                annotated = draw_hud(frame, status)
                _, jpeg = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 75])

            yield (b"--frame\r\n"
                   b"Content-Type: image/jpeg\r\n\r\n" + jpeg.tobytes() + b"\r\n")
            time.sleep(0.04)  # ~25 FPS max stream output

    @app.get("/video_feed")
    def video_feed():
        """MJPEG video stream endpoint for browsers."""
        return StreamingResponse(
            mjpeg_generator(),
            media_type="multipart/x-mixed-replace; boundary=frame"
        )

    @app.get("/api/status")
    def api_status():
        """Returns JSON snapshot of all tracking diagnostics and telemetry."""
        status: ControllerStatus = get_latest_status()
        telemetry = operator.get_telemetry()

        payload = {
            "tracking_enabled": status.enabled,
            "state": status.state.value,
            "last_thought": status.last_thought,
            "fps": round(status.fps, 1),
            "target": {
                "detected": status.target_box is not None,
                "center": status.target_center,
                "box": status.target_box,
                "confidence": round(status.target_confidence, 2),
                "error_x": status.error_x,
                "error_y": status.error_y,
            },
            "control": {
                "command": status.current_command,
                "moving_azimuth": status.moving_azimuth,
                "moving_altitude": status.moving_altitude,
                "pulse_remaining_s": round(status.pulse_remaining_s, 3),
            },
            "operator": {
                "connected": operator.is_connected,
                "host": operator.host,
                "port": operator.port,
            },
            "telemetry": {
                "received": telemetry.has_received,
                "base": telemetry.base,
                "shoulder": telemetry.shoulder,
                "elbow": telemetry.elbow,
                "wrist_pitch": telemetry.wrist_pitch,
                "wrist_roll": telemetry.wrist_roll,
                "age_s": round(status.telemetry_age_s, 3) if status.telemetry_age_s is not None else None,
            },
            "observation_age_s": round(status.observation_age_s, 3) if status.observation_age_s is not None else None,
            "fault": status.fault,
            "recent_logs": status.recent_logs,
        }
        payload["pose"] = {"available": bool(getattr(detector, "healthy", False)), "input": getattr(detector, "infer_size", None)}
        payload["pose_tuning"] = get_pose_tuning() if get_pose_tuning else {}
        payload["control_owner"] = "pivision-edge" if control_lease else "pivision-standalone" if standalone_control else "commander"
        payload["edge_control"] = control_lease.status() if control_lease else None
        return JSONResponse(payload)

    @app.post("/api/pose/tuning")
    def set_pose_tuning(payload: dict):
        if update_pose_tuning is None:
            raise HTTPException(status_code=404, detail="pose diagnostics unavailable")
        try:
            return update_pose_tuning(payload)
        except (TypeError, ValueError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.get("/api/v1/observations")
    def observations():
        if perception is None:
            raise HTTPException(status_code=503, detail="perception not initialized")
        return perception.snapshot()

    @app.put("/api/v1/perception")
    def set_perception(payload: dict):
        if perception is None:
            raise HTTPException(status_code=503, detail="perception not initialized")
        if set(payload) != {"enabled"} or type(payload["enabled"]) is not bool:
            raise HTTPException(status_code=422, detail="expected a boolean enabled field")
        if not payload["enabled"] and control_lease:
            control_lease.revoke()
        return perception.set_enabled(payload["enabled"])

    @app.get("/api/v1/control/status")
    def edge_status():
        if control_lease is None:
            raise HTTPException(409, "start PiVision with --edge-control")
        control_lease.service()
        return control_lease.status()

    @app.put("/api/v1/control/lease")
    def control_lease_update(payload: dict):
        if control_lease is None:
            raise HTTPException(409, "start PiVision with --edge-control")
        if payload.get("enabled") is True and payload.get("renew") is not True:
            speed, age = payload.get("speed_percent", 20), payload.get("max_observation_age_s", 0.35)
            if type(speed) is not int or not 1 <= speed <= 100 or type(age) not in (int, float) or not 0.05 <= age <= 1.0:
                raise HTTPException(422, "speed must be 1..100 and observation age 0.05..1.0 seconds")
            if control_lease.owner is None:
                controller.speed_percent, controller.max_observation_age = speed, age
                if "acceptable_ratio" in payload:
                    control_lease.tune(payload.get("owner"), payload["acceptable_ratio"])
        return control_lease.update(payload.get("owner"), payload.get("enabled"), payload.get("renew") is True)

    @app.put("/api/v1/control/tuning")
    def control_tuning(payload: dict):
        if control_lease is None:
            raise HTTPException(409, "start PiVision with --edge-control")
        return control_lease.tune(payload.get("owner"), payload.get("acceptable_ratio"))

    @app.post("/api/v1/control/commands")
    def manual_edge_command(payload: dict):
        if control_lease is None:
            raise HTTPException(409, "start PiVision with --edge-control")
        try:
            command = payload["command"]
            if type(command) is not int:
                raise ValueError("command must be an integer")
            packet = bytes.fromhex(payload["payload_hex"])
        except (KeyError, TypeError, ValueError) as error:
            raise HTTPException(422, str(error)) from error
        return control_lease.manual_command(command, packet)

    def require_standalone():
        if not standalone_control:
            raise HTTPException(status_code=409, detail="PiVision is perception-only; control the robot through Commander")

    @app.post("/api/tracking/enable")
    def enable_tracking():
        require_standalone()
        if not controller.set_enabled(True):
            raise HTTPException(status_code=409, detail=controller.last_thought)
        return {"status": "ok", "tracking_enabled": True}

    @app.post("/api/tracking/disable")
    def disable_tracking():
        controller.set_enabled(False)
        return {"status": "ok", "tracking_enabled": False}

    @app.post("/api/tracking/toggle")
    def toggle_tracking():
        require_standalone()
        new_state = not controller.enabled
        if not controller.set_enabled(new_state):
            raise HTTPException(status_code=409, detail=controller.last_thought)
        return {"status": "ok", "tracking_enabled": controller.enabled}

    @app.post("/api/command/stop")
    def stop_robot():
        controller.set_enabled(False)
        return {"status": "ok", "message": "Tracking disabled and stop dispatched if moving"}

    @app.post("/api/command/home")
    def home_robot():
        require_standalone()
        controller.stop_movement("Homing requested")
        controller.set_enabled(False)
        success = operator.home(delay_ms=0)
        return {"status": "ok" if success else "failed", "homing_dispatched": success}

    @app.post("/api/command/enable_control")
    def enable_control():
        require_standalone()
        controller.set_enabled(False)
        success = operator.clear_fault()
        return {"status": "ok" if success else "failed", "control_enable_requested": success}

    @app.post("/api/command/set_speed")
    def set_speed(percent: int = 20):
        require_standalone()
        if controller.enabled:
            raise HTTPException(status_code=409, detail="disable tracking before changing controller speed")
        success = operator.erv_set_speed_percent(percent)
        return {"status": "ok" if success else "failed", "speed_percent": percent}

    @app.get("/", response_class=HTMLResponse)
    def index():
        """Super simple, clean dark-mode web dashboard showing what the Pi is thinking."""
        html = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>TALOS Pi Edge Tracker</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { height: 100vh; overflow: hidden; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #121417; color: #e0e4eb; padding: 18px; }
    header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #282c34; padding-bottom: 12px; margin-bottom: 18px; }
    h1 { font-size: 1.4rem; color: #61afef; letter-spacing: 0.5px; }
    .badge { font-weight: bold; padding: 4px 10px; border-radius: 4px; font-size: 0.85rem; }
    .badge.TRACKING { background: #e5c07b; color: #1e1e1e; }
    .badge.CENTERED { background: #98c379; color: #1e1e1e; }
    .badge.SEARCHING { background: #61afef; color: #1e1e1e; }
    .badge.WAITING_FEEDBACK { background: #d19a66; color: #1e1e1e; }
    .badge.DISABLED { background: #4b5263; color: #e0e4eb; }
    .badge.LIMIT, .badge.FAULT { background: #e06c75; color: #fff; }

    .controls { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 18px; }
    button { font-size: 0.95rem; font-weight: bold; padding: 10px 16px; border: none; border-radius: 6px; cursor: pointer; transition: 0.15s; }
    .btn-toggle { background: #98c379; color: #121417; }
    .btn-toggle.active { background: #e06c75; color: #fff; }
    .btn-stop { background: #d19a66; color: #121417; }
    .btn-home { background: #3e4451; color: #abb2bf; }
    .btn-action { background: #2c313a; color: #61afef; border: 1px solid #61afef; }
    button:hover { opacity: 0.85; }

    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; height: calc(100vh - 185px); min-height: 0; }
    @media (max-width: 900px) { .grid { grid-template-columns: 1fr; } }

    .panel { background: #1e2227; border-radius: 8px; padding: 16px; border: 1px solid #282c34; min-height: 0; overflow: auto; }
    .panel h2 { font-size: 1.05rem; color: #abb2bf; margin-bottom: 12px; text-transform: uppercase; letter-spacing: 0.5px; border-bottom: 1px solid #2c313a; padding-bottom: 6px; }

    .stream-container { text-align: center; }
    .stream-container img { width: 100%; max-height: 480px; object-fit: contain; border-radius: 6px; background: #000; border: 1px solid #333; }

    .thought-box { background: #282c34; border-left: 4px solid #61afef; padding: 12px; border-radius: 4px; font-size: 1.05rem; margin-bottom: 14px; font-weight: 500; min-height: 48px; display: flex; align-items: center; }
    
    .data-table { width: 100%; border-collapse: collapse; font-family: monospace; font-size: 0.95rem; }
    .data-table td { padding: 6px 4px; border-bottom: 1px solid #2c313a; }
    .data-table td:first-child { color: #abb2bf; width: 45%; }
    .data-table td:last-child { color: #98c379; font-weight: bold; }

    .log-box { background: #181a1f; border-radius: 4px; padding: 8px; font-family: monospace; font-size: 0.8rem; height: 160px; overflow-y: auto; color: #abb2bf; }
    .log-entry { margin-bottom: 3px; }
    .tuning { display:flex; align-items:center; gap:8px; margin-bottom:18px; flex-wrap:wrap; }
    .tuning label { color:#abb2bf; font-size:.8rem; text-transform:uppercase; letter-spacing:.04em; }
    .tuning input { width:62px; background:#181a1f; color:#98c379; border:1px solid #3e4451; border-radius:4px; padding:7px 6px; font-family:monospace; font-size:.9rem; }
    .tuning input:focus { outline:none; border-color:#61afef; }
    .identity-grid { display:flex; gap:8px; overflow-x:auto; padding:4px 0; }
    .face-card { width:94px; flex:0 0 94px; background:#181a1f; border:1px solid #3e4451; border-radius:5px; padding:4px; color:#abb2bf; font-size:.72rem; }
    .face-card img { display:block; width:84px; height:84px; object-fit:cover; border-radius:3px; margin-bottom:4px; }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>TALOS Pi Edge Closed-Loop Tracker</h1>
      <small style="color: #5c6370;">Raspberry Pi 4 Autonomous Visual Servoing</small>
    </div>
    <div id="status-badge" class="badge DISABLED">DISABLED</div>
  </header>

  <div class="controls">
    <button id="toggle-btn" class="btn-toggle" onclick="toggleTracking()">START TRACKING</button>
    <button class="btn-stop" onclick="stopRobot()">HALT MOTION</button>
    <button class="btn-action" onclick="enableControl()">RE-ENABLE SERVOS (CON)</button>
    <button class="btn-action" onclick="setSpeed(20)">SPEED 20%</button>
    <button class="btn-action" onclick="setSpeed(35)">SPEED 35%</button>
    <button class="btn-action" onclick="setSpeed(50)">SPEED 50%</button>
    <button class="btn-home" onclick="homeRobot()">HOME ROBOT</button>
  </div>
  <div class="tuning">
    <label>ROI</label><input id="roi-x" value="0" title="ROI X"><input id="roi-y" value="0" title="ROI Y"><input id="roi-w" value="1" title="ROI Width"><input id="roi-h" value="1" title="ROI Height">
    <label>Pose conf.</label><input id="person-conf" value="0.35">
    <button class="btn-action" onclick="savePoseTuning()">APPLY</button></div>

  <div class="grid">
    <div class="panel">
      <h2>Live Annotated Feed</h2>
      <div class="stream-container">
        <img src="/video_feed" alt="Live Stream">
      </div>
    </div>

    <div class="panel">
      <h2>Pi Thinking & Diagnostics</h2>
      <div id="thought" class="thought-box">Waiting for status...</div>

      <table class="data-table">
        <tr><td>Autonomous Tracking</td><td id="t-enabled">OFF</td></tr>
        <tr><td>Inference Rate</td><td id="t-fps">0 FPS</td></tr>
        <tr><td>Observation Age</td><td id="t-observation-age">-</td></tr>
        <tr><td>Target Center (X, Y)</td><td id="t-target">-</td></tr>
        <tr><td>Error Vector (dX, dY)</td><td id="t-error">-</td></tr>
        <tr><td>Active Motion Command</td><td id="t-cmd">NONE</td></tr>
        <tr><td>Operator Connection</td><td id="t-op">DISCONNECTED</td></tr>
        <tr><td>Joint Base Position</td><td id="t-base">-</td></tr>
        <tr><td>Joint Shoulder / Elbow</td><td id="t-arm">-</td></tr>
        <tr><td>Wrist Pitch</td><td id="t-pitch">-</td></tr>
        <tr><td>Telemetry Age</td><td id="t-telemetry-age">-</td></tr>
        <tr><td>Latched Fault</td><td id="t-fault">NONE</td></tr>
        <tr><td>Pose Gate</td><td id="t-pose">Loading…</td></tr>
        <tr><td>ROI</td><td id="t-roi">-</td></tr>
      </table>

      <h2 style="margin-top: 14px;">Recent Action Log</h2>
      <div id="logs" class="log-box"></div>
    </div>
  </div>

  <script>
    async function updateStatus() {
      try {
        const res = await fetch('/api/status');
        if (!res.ok) return;
        const d = await res.json();

        // Badge & Toggle
        const badge = document.getElementById('status-badge');
        badge.innerText = d.state;
        badge.className = 'badge ' + d.state;

        const toggleBtn = document.getElementById('toggle-btn');
        if (d.tracking_enabled) {
          toggleBtn.innerText = 'STOP TRACKING';
          toggleBtn.className = 'btn-toggle active';
        } else {
          toggleBtn.innerText = 'START TRACKING';
          toggleBtn.className = 'btn-toggle';
        }

        // Thought
        document.getElementById('thought').innerText = d.last_thought || 'Idle';

        // Diagnostics
        document.getElementById('t-enabled').innerText = d.tracking_enabled ? 'ON' : 'OFF';
        document.getElementById('t-fps').innerText = d.fps + ' FPS';
        document.getElementById('t-observation-age').innerText = d.observation_age_s === null ? '-' : d.observation_age_s.toFixed(3) + ' s';
        document.getElementById('t-target').innerText = d.target.detected ? `${d.target.center[0]}, ${d.target.center[1]} (${(d.target.confidence * 100).toFixed(0)}%)` : 'No Target';
        document.getElementById('t-error').innerText = d.target.detected ? `dX: ${d.target.error_x} px, dY: ${d.target.error_y} px` : '-';
        document.getElementById('t-cmd').innerText = d.control.command;
        document.getElementById('t-op').innerText = d.operator.connected ? `CONNECTED (${d.operator.host}:${d.operator.port})` : 'DISCONNECTED';
        document.getElementById('t-base').innerText = d.telemetry.received ? d.telemetry.base + ' counts' : 'No Telemetry';
        document.getElementById('t-arm').innerText = d.telemetry.received ? `Sh: ${d.telemetry.shoulder}, El: ${d.telemetry.elbow}` : '-';
        document.getElementById('t-pitch').innerText = d.telemetry.received ? d.telemetry.wrist_pitch + ' counts' : '-';
        document.getElementById('t-telemetry-age').innerText = d.telemetry.age_s === null ? '-' : d.telemetry.age_s.toFixed(3) + ' s';
        document.getElementById('t-fault').innerText = d.fault || 'NONE';
        document.getElementById('t-pose').innerText = d.pose && d.pose.available ? `ONNX ${d.pose.input[0]}x${d.pose.input[1]}` : 'UNAVAILABLE';
        const tuning = d.pose_tuning || {};
        document.getElementById('t-roi').innerText = [tuning.roi_x,tuning.roi_y,tuning.roi_w,tuning.roi_h].map(v => Number(v ?? 0).toFixed(2)).join(', ');

        // Logs
        const logBox = document.getElementById('logs');
        logBox.replaceChildren();
        if (d.recent_logs && d.recent_logs.length) {
          d.recent_logs.forEach(line => {
            const entry = document.createElement('div');
            entry.className = 'log-entry';
            entry.textContent = line;
            logBox.appendChild(entry);
          });
        }
      } catch (err) {
        console.error('Status fetch error:', err);
      }
    }

    async function toggleTracking() {
      const response = await fetch('/api/tracking/toggle', { method: 'POST' });
      if (!response.ok) {
        const error = await response.json();
        alert(error.detail || 'Tracking request was rejected');
      }
      updateStatus();
    }

    async function savePoseTuning() {
      const body = {roi_x:+document.getElementById('roi-x').value,roi_y:+document.getElementById('roi-y').value,roi_w:+document.getElementById('roi-w').value,roi_h:+document.getElementById('roi-h').value,person_confidence:+document.getElementById('person-conf').value};
      const response = await fetch('/api/pose/tuning', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      if (!response.ok) alert((await response.json()).detail || 'Invalid perception settings');
    }

    async function stopRobot() {
      await fetch('/api/command/stop', { method: 'POST' });
      updateStatus();
    }

    async function enableControl() {
      await fetch('/api/command/enable_control', { method: 'POST' });
      updateStatus();
    }

    async function setSpeed(val) {
      await fetch('/api/command/set_speed?percent=' + val, { method: 'POST' });
      updateStatus();
    }

    async function homeRobot() {
      if (confirm('Home the robot now? Bingo will move to physical calibration limits.')) {
        await fetch('/api/command/home', { method: 'POST' });
        updateStatus();
      }
    }

    setInterval(updateStatus, 200);
    updateStatus();
  </script>
</body>
</html>"""
        return HTMLResponse(content=html)

    return app
