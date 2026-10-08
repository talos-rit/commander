# TALOS Pi Edge Tracker

Experimental visual tracking service for Bingo. It runs person detection on Bluey,
uses the existing Operator ICD connection at `127.0.0.1:61616`, and exposes a local
diagnostic dashboard on port 5050.

Commander integration now uses `--edge-control`: PiVision performs detection and
bounded motion locally, while Commander owns an expiring control lease and sends
manual commands through PiVision's HTTP gateway. This avoids both per-frame network
round trips and competing TCP clients on the single-client Operator server.
Without a control flag, startup is perception-only; GUI robot commands require the
explicit legacy `--standalone-control` flag. The staged Bluey integration runs on
port **5051**, separately from the existing `/home/pi/test/tracker` deployment.

Integrated endpoints:

- `GET /api/v1/observations`: latest frame sequence, session ID, dimensions, bounding
  boxes, torso aim points, keypoints, inference duration and producer-relative age.
- `PUT /api/v1/perception`: `{"enabled": false}` pauses inference and revokes control.
- `GET /api/v1/control/status`: current owner, lease, Operator connection and feedback.
- `PUT /api/v1/control/lease`: explicit arming/release with an owner token; renewals
  cannot revive an expired or revoked lease. TTL is 1.5 seconds.
- `POST /api/v1/control/commands`: implemented ER-V ICD command plus hex payload;
manual motion is rejected while automation owns control. Stop/Home revoke it.

- `PUT /api/v1/control/tuning`: `{"owner": "<Commander token>", "acceptable_ratio": 0.15}`
  updates the centering box while tracking stays enabled. Valid ratios are 0.05–0.8;
  the active lease owner is required while automation is on. This does not renew or
  rearm the lease. Commander exposes the same setting through its live slider.

Commander URL configuration selects its HTTP Publisher adapter, so PiVision remains
the only TCP client connected to `127.0.0.1:61616`. Operator still owns serial, ACL
arbitration, physical command execution and its unchanged 500 ms jog watchdog.

## Control design

The running tracker follows the target with Pi-local continuous jog commands:

1. The camera thread overwrites one latest-frame slot; frames are never queued.
2. Inference consumes each newest sequence at most once. The web stream reads a copy
   and cannot steal a control frame.
3. A fresh off-center observation selects base or pitch and updates its jog direction.
4. A separate 60 Hz service refreshes the jog every 150 ms while camera observations
   remain current. Operator retains its independent 500 ms watchdog.
5. Centering, losing the target, disabling tracking, losing camera updates, or a
   controller fault stops the jog. No per-frame Commander request is needed.

This matches the real ER-V constraint that telemetry and manual motion share one ACL
serial parser. Telemetry is optional: missing or stale feedback does not prevent
enabling tracking or base/pitch corrections. Fresh counts can
still apply the configured count limits; stale counts are not used. Loss of target,
stale video, socket loss, detector failure, or a reported controller fault stops motion.

ONNX Runtime is the production detector. Missing/broken ONNX fails startup or disables
tracking; HOG/Ultralytics fallback is available only with
`ALLOW_DETECTOR_FALLBACK=1` for non-autonomous experiments.

Pitch tracking uses Operator's existing wrist-pitch path by default. Optional
`PITCH_MIN_COUNT` and `PITCH_MAX_COUNT` add custom count limits; leaving them unset
does not disable pitch. Base tracking uses the existing `-5000..5000` count guard.

## Dashboard and API

Open `http://bluey.local:5050` after starting the service. Useful endpoints are:

- `GET /api/status`
- `POST /api/tracking/enable`
- `POST /api/tracking/disable`
- `POST /api/command/stop`
- `POST /api/command/enable_control` (one explicit `CON` request)
- `POST /api/command/home`

Enabling tracking returns HTTP 409 unless Operator is connected, telemetry is fresh,
and no controller fault is latched. Faults are never cleared periodically in the
background. The dashboard's re-enable action disables tracking first and sends one
explicit request. `ACK` means only that Operator accepted the packet, not that Bingo
moved or that a physical fault cleared.

## Configuration

The most useful environment variables are:

```text
CAMERA_SOURCE=rtsp://localhost:8554/camera
MODEL_WEIGHTS=yolo26n.onnx
CONF_THRESHOLD=0.35
DEFAULT_SPEED=20
DEADBAND_RATIO=0.32
TELEMETRY_TIMEOUT=1.25
MAX_OBSERVATION_AGE=0.35
SETTLE_TIME=0.12
MIN_PULSE=0.055
MAX_BASE_PULSE=0.16
MAX_PITCH_PULSE=0.09
PITCH_MIN_COUNT=
PITCH_MAX_COUNT=
```

Keep every pulse below Operator's independent 500 ms continuous-motion watchdog.

## Local verification

From the senior-project directory:

```powershell
uv run --project commander python -m pytest test/pi_tracker -q
```

The tests cover packet/listener handling, stale telemetry/video gating, fault latching,
bounded pulse stops independent of inference, post-motion feedback gating, frame-slot
behavior, ONNX output formats, and detector fail-closed startup. They do not prove
camera performance, controller acceptance, or physical behavior.

## Deployment

The included script copies this directory to `/home/pi/test/tracker`:

```powershell
.\scripts\deploy_to_pi.bat
```

Then, with Bingo's workspace clear and a person supervising the hardware:

```bash
ssh pi@bluey.local
cd /home/pi/test/tracker
./scripts/start_tracker.sh
```

The script creates `/home/pi/test/tracker/venv` and installs from the bundled ARM64
wheels. It does not install or manage a systemd service. Before deploying, inspect the
actual Pi Operator tree, process/TTY ownership, and current tracker files; the Pi may
contain newer uncommitted fixes.

First physical validation should use one small base-only correction at 20%, confirm a
clean stop, confirm `TELP` resumes, and inspect Operator logs for any concatenated ACL
commands. Do not describe the tracker as physically verified until that supervised test
has been completed.
