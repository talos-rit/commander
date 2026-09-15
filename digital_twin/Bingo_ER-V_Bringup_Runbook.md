# Bingo / Scorbot ER-V Bring-Up and Digital Twin Runbook

_Last verified: 2026-09-15_

This documents the exact path that successfully moved the physical Scorbot through Commander and the digital twin. The goal is to avoid repeating the serial/controller archaeology next time.

## Current known-good architecture

- Physical robot: Bingo, Scorbot ER-V / ACL controller
- Raspberry Pi hostname currently used for Bingo: `bluey.local`
- Pi Operator TCP port: `61616`
- Pi serial device: `/dev/ttyUSB0`
- USB serial adapter: Prolific PL2303 (`067b:2303`)
- Controller serial settings: 9600 baud, 8 data bits, 1 stop bit, no parity, XON/XOFF software flow control
- Commander talks TCP to Operator.
- Operator talks ACL over `/dev/ttyUSB0` to the Scorbot controller.
- The current digital twin can register a real Commander `Publisher` and switch the selected robot from `virtual` to `real`.
- The PyBullet view is still a command estimate when using the real backend. It is not physical telemetry.

## Important current limitation

The ER-V Operator currently implements only:

- Handshake
- Polar pan discrete
- Home
- Polar pan continuous start
- Polar pan continuous stop

Commander exposes many more methods than the ER-V Operator implements.

In particular, the twin's W/S "extend/retract" controls use Cartesian Y commands. Those do **not** work on Bingo today because the ER-V Operator does not implement Cartesian movement.

The current ER-V polar mapping is:

- Azimuth -> base axis
- Altitude -> wrist pitch axis

Shoulder and elbow manual-mode keycodes already exist in Operator source, but they are not exposed through the network protocol.

---

# Normal future startup

## 1. Physical/network setup

1. Power the Talos router.
2. Connect the laptop to the Talos network. Ethernet worked reliably.
3. Power the Raspberry Pi.
4. Power the Scorbot controller.
5. Keep the robot workspace clear before motor power or homing.

From Windows PowerShell:

```powershell
Test-NetConnection bluey.local -Port 61616
```

If Operator is already running, the desired result is:

```text
TcpTestSucceeded : True
```

Windows may first print a failed IPv6 attempt for the `fe80::...` address. That was harmless as long as it then reached `bluey.local` over IPv4 and reported `TcpTestSucceeded : True`.

## 2. SSH to the Pi

```powershell
ssh pi@bluey.local
```

Use the current team-managed credentials. Do not store passwords in this runbook.

## 3. Verify the serial device

On the Pi:

```bash
ls -l /dev/ttyUSB0
fuser -v /dev/ttyUSB0
cat /etc/talos/configs/operator.conf
```

Expected device:

```text
/dev/ttyUSB0
```

Known config at the time of testing:

```text
scorbot_dev: /dev/ttyUSB0
socket_address: 0.0.0.0
socket_port: 61616
```

`lsof` was not installed on the Pi, so `fuser` is the easiest ownership check.

Only one process should own `/dev/ttyUSB0`.

## 4. Configure the serial port before starting Operator

This is currently important because Operator opens the tty but does not configure the termios settings itself.

Run:

```bash
stty -F /dev/ttyUSB0 9600 cs8 -cstopb -parenb -crtscts raw -echo ixon ixoff
```

Then confirm:

```bash
stty -F /dev/ttyUSB0 -a
```

Important values:

```text
speed 9600 baud
cs8
-parenb
-cstopb
-crtscts
ixon
ixoff
```

The order in the setup command matters slightly: `raw` disables several tty features, so `ixon ixoff` are explicitly re-enabled afterward.

## 5. If the ACL controller is behaving normally, start Operator

```bash
/home/pi/operator2/operator/build/bin/erv
```

Leave that terminal open.

Operator log:

```text
/etc/talos/logs/operator.log
```

From the laptop, verify again:

```powershell
Test-NetConnection bluey.local -Port 61616
```

## 6. Verify Commander -> Operator with a handshake

From:

```text
D:\GitHub\senior_project\commander
```

run:

```powershell
uv run python -c "import time; from src.connection.publisher import Publisher; p=Publisher('bluey.local',61616); time.sleep(2); p.handshake(); time.sleep(2); p.close()"
```

Known-good output includes:

```text
Connected to socket: bluey.local:61616
RECEIVED MESSAGE: ACK
```

Important: this ACK means the Pi-side Operator accepted the network command. It does **not** prove the Scorbot controller executed a serial command.

## 7. Home after a fresh controller startup

A freshly booted Scorbot should be homed before normal movement.

Clear the robot workspace and have someone ready at the physical stop/power controls.

With Operator running, the intended Commander path is:

```powershell
uv run python -c "import time; from src.connection.publisher import Publisher; p=Publisher('bluey.local',61616); time.sleep(1); p.home(0); time.sleep(35); p.close()"
```

Operator's ER-V home sequence is:

```text
DEFP DELTA
HOME
HERE DELTA
```

The manually tested ACL equivalent successfully homed the robot.

Do not continue with ordinary motion if homing reports a failure.

## 8. Tiny known-good movement smoke test

After homing:

```powershell
uv run python -c "import time; from src.connection.publisher import Publisher; p=Publisher('bluey.local',61616); time.sleep(2); p.handshake(); time.sleep(1); p.polar_pan_discrete(1,0,0,1000); time.sleep(4); p.close()"
```

This requests approximately +1 degree of base/azimuth movement.

The ER-V Operator converts base degrees using approximately 42.5666 encoder counts per degree.

Only move to larger tests after this succeeds.

---

# Launching the digital twin against the real robot

From:

```text
D:\GitHub\senior_project\commander
```

run:

```powershell
uv run --extra simulation python -m src.simulation.viewer --no-demo --real-robot bluey=bluey.local:61616
```

The viewer always creates the simulated `bluey` model. The `--real-robot` argument additionally creates a real Commander `Publisher` for the same robot ID.

In the control panel:

```text
Robot: bluey
Backend: real
```

The physical robot is Bingo even though the current logical/hostname label is `bluey`.

## Controls currently appropriate for real Bingo

Known/expected ER-V-supported controls:

- Polar discrete azimuth
- Polar discrete altitude
- Polar continuous base movement
- Polar continuous wrist-pitch movement
- Polar stop
- Home

Current twin controls that should **not** be treated as supported real ER-V controls:

- W/S Cartesian extend/retract
- Cartesian X/Y/Z buttons
- Speed slider / `set_speed`
- Absolute simulated presets 1/2/3
- Other broad Commander API calls with no matching ER-V Operator implementation

The PyBullet motion in real mode is a command estimate. The physical robot does not currently return enough state telemetry to make it a true physical pose display.

---

# Recovery procedure for the weird "echo-only" ACL state

This was the major failure encountered during bring-up.

## Symptoms

TCP and Operator looked healthy:

```text
Connected to socket: bluey.local:61616
RECEIVED MESSAGE: ACK
```

But the physical robot did not move.

The Operator log showed heavily mangled text with fragments such as:

```text
SHIFT DELTA BY 1 -42
clrbuf
MOVE DELTA
ACL ... unrecognized request
```

Direct serial tests showed:

```text
VER -> VER
HELP -> HELP
```

with no ACL prompt, no version response, and no command execution.

## What fixed it

1. Stop Operator.
2. Ensure nothing else owns `/dev/ttyUSB0`.
3. Apply the documented serial configuration:

```bash
stty -F /dev/ttyUSB0 9600 cs8 -cstopb -parenb -crtscts raw -echo ixon ixoff
```

4. Leave robot motor power off.
5. Power-cycle the Scorbot controller/logic.
6. Allow it to boot fully.

The successful boot produced:

```text
----RAM TEST COMPLETE.

----ROM TEST COMPLETE.

USER RAM CHECKPOINT ERROR !
INSTALLING DEFAULT SETUP.
SYSTEM READY !
>
```

After that, direct ACL commands behaved normally.

`VER` returned:

```text
--- ESHED ROBOTEC ---
VERSION: 1.31
DATE : 15/08/89
>
```

`HELP` returned the normal ACL command list.

Once the controller was in this sane DIRECT-mode state, homing and movement worked.

## Quick direct-serial sanity test

Only do this while Operator is stopped.

Terminal 1:

```bash
cat /dev/ttyUSB0
```

Terminal 2:

```bash
printf 'VER\r' > /dev/ttyUSB0
```

A healthy controller should return the ACL version and a `>` prompt, not merely echo `VER`.

Do not run another process against `/dev/ttyUSB0` while Operator is using it.

---

# Hardware/controller notes discovered during bring-up

## PL2303 adapter

Observed USB device:

```text
067b:2303 Prolific Technology, Inc. PL2303 Serial Port / Mobile Phone Data Cable
```

Linux driver:

```text
pl2303
```

The adapter worked correctly after the controller was reset into a sane state.

## Modem-control lines

Observed:

```text
DTR: ON
RTS: ON
CTS: OFF
CD : OFF
DSR: OFF
```

The original Scorbot cable documentation describes local handshake loops that are not reflected by these modem-line readings. Despite that, normal serial communication worked, so this was not the immediate blocker.

## USER RAM CHECKPOINT ERROR

The controller reported:

```text
USER RAM CHECKPOINT ERROR !
INSTALLING DEFAULT SETUP.
```

but then reached:

```text
SYSTEM READY !
>
```

and operated normally.

This likely means the battery-backed user RAM/checkpoint was not valid. The controller backup battery should be investigated later, especially if saved controller state/programs need to survive power cycles.

---

# Important software findings

## Operator does not currently configure the tty

In the ER-V `Scorbot` constructor, Operator opens the configured serial device but does not currently perform the needed termios setup.

That is why the explicit `stty` command belongs in the startup procedure for now.

A future cleanup should move the known-good 9600/8N1/XON-XOFF configuration into Operator itself.

## Operator command surface is much smaller than Commander

Current ER-V Operator command IDs:

```text
0x0000 Handshake
0x0001 PolarPan
0x0002 Home
0x0003 PolarPanStart
0x0004 PolarPanStop
```

Commander defines many additional commands, but the ER-V Operator rejects unknown command IDs.

An ACK from the network server therefore must not be interpreted as hardware-level completion.

## Existing ER-V manual-axis definitions

Operator already defines ACL manual-mode characters for:

```text
Base -
Base +
Shoulder -
Shoulder +
Elbow -
Elbow +
Wrist pitch -
Wrist pitch +
Wrist roll -
Wrist roll +
```

The existing continuous polar implementation exposes only:

```text
base
wrist pitch
```

Shoulder and elbow are the obvious next narrow capability to expose for physical arm jogging.

---

# Recommended next implementation

Do **not** pretend the ER-V has Cartesian support just to make W/S work.

The smallest clean next step is explicit real-hardware joint jogging for:

```text
shoulder +/-
elbow +/-
```

over Commander's existing hardware-specific operation path.

Keep this distinct from simulated Cartesian W/S behavior until real kinematics and coordinate calibration exist.

Acceptance should be based on tiny, manually supervised jogs with immediate stop-on-release behavior.

---

# Known-good final status on 2026-09-15

Verified:

- Laptop -> Pi network connectivity
- Commander -> Operator TCP connection
- Commander handshake ACK
- Pi -> PL2303 -> Scorbot serial TX/RX
- Healthy ACL cold boot
- ACL 1.31 responding to `VER` and `HELP`
- Robot homing
- Tiny discrete polar movement
- Physical movement from the digital twin real backend
- Base/polar controls working through the twin

Still missing:

- Physical shoulder/elbow arm jog through the network/twin
- True real-robot telemetry
- Cartesian ER-V movement
- Reliable command completion/rejection responses
- Automatic tty configuration inside Operator
