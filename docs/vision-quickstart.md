# Commander vision quick start

The `main` branch includes the PiVision integration. It works from a single
Commander checkout; no sibling worktree or shared Python environment is needed.

## Get the app

Install Git, uv, and Node.js with npm (or Bun), then run:

```sh
git clone --branch main https://github.com/talos-rit/commander.git
cd commander
uv sync --locked
cd web
npm install
npm run build
cd ..
uv run commander-web
```

If you already have the repository, switch to `main` and run
`git pull --ff-only`, then repeat the dependency installation and frontend build.
With Bun, use `bun install --frozen-lockfile` and `bun run build` instead of npm.
Python must be 3.12; uv can install the required version for you.

Open <http://127.0.0.1:8000>. After setup, Windows users can double-click
`start_commander.bat`, or run `tools/Start-VisionConsole.ps1` in PowerShell.
The Windows launcher checks the local Python environment and frontend build.
Its restart option only replaces a console launched by this checkout.

## Connect to PiVision

Your computer must reach the robot's camera stream and PiVision HTTP service.
PiVision and a compatible Operator must already be running on the Pi; installing
Commander does not install or restart either service.

In **Settings**, add or edit a robot and configure its Operator host, port
(`61616` for Bingo), camera stream URL, and PiVision URL
(`http://bluey.local:5051` for the existing Bluey setup). Assign it to Camera 1
and save. The equivalent minimal `config/robot_configs.local.yaml` entry is:

```yaml
bluey.local:
  socket_host: bluey.local
  socket_port: 61616
  camera_index: rtsp://bluey.local:8554/camera
  pi_vision_url: http://bluey.local:5051
  pi_vision_speed_percent: 20
  pi_vision_max_age_s: 0.35
```

Replace the sample camera URL with the stream configured on your Pi. Local config
files are ignored by Git, so teammates keep their own robot settings.
With a PiVision URL, Commander sends manual commands through the PiVision gateway
and PiVision owns the Operator TCP connection. Pi-local tracking does not require
the workstation YOLO extra. For workstation YOLO tracking without PiVision, run
`uv sync --extra yolo`.

Check that video and PiVision status arrive before enabling **Auto-Track**.
Auto-Track arms physical following; **Pause PiVision** separately pauses inference
and revokes automation. Manual jogging requires Debug mode and Auto-Track off.
Home moves the physical robot. Coordinate access to the shared robot with your
teammates before using motion controls.

If the UI fails to load, rebuild `web/dist`. If PiVision status is unavailable,
check the PiVision URL and network access. Use the
[integration notes](pivision-integration.md) for control ownership, deployment
details, and previously measured behavior; those notes describe historical trials,
not a guarantee of the current robot's state.
