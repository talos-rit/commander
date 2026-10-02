# Simulation coordinates and units

`SimulatedRobot` is a deterministic behavioral model, not a calibrated Scorbot
kinematic model. Its values preserve Commander/ICD command values; they must not be
silently interpreted as physical robot joint coordinates.

## Coordinate assumptions

- `RobotPose.azimuth` is expressed in the raw numeric units accepted by the ICD's
  discrete polar-pan `Delta Azimuth` field. The current ICD does not define whether
  that value is degrees, tenths of degrees, encoder counts, or another unit.
- `RobotPose.altitude` is expressed in the raw numeric units accepted by the ICD's
  discrete polar-pan `Delta Altitude` field. Its physical unit is likewise undefined.
- `RobotPose.x`, `y`, and `z` use the Cartesian discrete-move convention documented
  by the ICD: tenths of a millimetre.
- Polar and Cartesian fields are independent logical axes. Updating one coordinate
  system does not update the other. There is currently no forward or inverse
  kinematic transform between them.
- These values are not PyBullet joint angles, URDF coordinates, motor encoder counts,
  or calibrated physical-camera poses.

## Time and velocity assumptions

- All timestamps and durations inside the simulator are seconds on its supplied
  `ManualClock`.
- ICD delay/duration values passed through `SimulatedPublisher` are milliseconds and
  are converted to seconds at that boundary.
- Each configured velocity is expressed as that axis's coordinate units per simulated
  second. Polar velocity therefore remains raw polar units/second until the ICD is
  clarified; Cartesian velocity is tenths of a millimetre/second.
- `set_speed(0..255)` is modeled as a scalar from zero to one applied to configured
  per-axis speeds. That relationship is a simulation convention, not a claim about
  either physical controller.
- Requested durations may slow a move, but the simulator will not exceed configured
  axis speeds to meet a shorter duration.

## Before physical or PyBullet calibration

The project must choose and document a canonical pose contract, verify both robot
controllers' polar units, define robot/camera coordinate frames, and provide explicit
conversion functions. Those conversions should sit at the backend boundary rather
than changing the semantic Director API or reinterpreting existing saved simulations.

## 3D state viewer

The PyBullet viewer follows this one-way data flow:

`Publisher -> SimulatedRobot -> RobotStateSnapshot -> PyBulletRobotViewer`

The viewer has no Publisher and exposes no command methods. This keeps it reusable
for a future physical telemetry adapter and for recorded trajectories. See
[`VIEWER.md`](VIEWER.md) for commands, architecture, and mapping limitations.
