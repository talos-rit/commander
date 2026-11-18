# Web arm visualization

The Debug rail's Digital twin section renders the same eight STL meshes as the
desktop PyBullet viewer, using three.js. `ArmScene.tsx` imports them directly from
`../digital_twin/sboter4u_model/meshes` (Vite copies them into `dist/assets`), and
is lazy-loaded so three.js stays out of the main bundle. The view can be orbited
and zoomed (double-click resets); it has no command path.

`src/armGeometry.json` records the joint origin, RPY, axis, and limits from
`../digital_twin/sboter4u_model/robots/sboter4u_model.URDF`. Keep it synchronized
when changing that model. `armKinematics.ts` applies URDF origin transforms before
joint rotations and clamps the displayed joint angles as the desktop viewer does;
`linkPoses` gives each link frame, which is also its mesh frame. The scene applies
the desktop viewer's `LEGACY_MODEL_LEVEL_RPY` correction to the tilted CAD base
and sits the pedestal on the grid.

The status API adds `telemetry.joint_positions` in URDF radians. Python reuses
`BASE_CALIBRATION` and `map_arm_controller_coordinates` from the desktop twin.
The latter subtracts shoulder delta from the elbow because the controller reports
independent forearm orientation. Do not duplicate that calibration in JavaScript.
Only timestamped joint-coordinate frames supply a pose; raw encoders and command
ACKs cannot. Four-coordinate frames omit base yaw. Base absolute yaw remains
unverified; roll and gripper are fixed visual references, not measured feedback.
Telemetry older than 1.5 seconds is dimmed and labeled stale. Disconnected robots
show no pose. No animation predicts or extrapolates physical motion.

## Dual-arm deployment

The web UI supports stable robot names independent of the Pi hostname and saved
native/ESP controller profiles. Operator must report a matching profile before
motion controls unlock. ESP demo has base controls only and no pose telemetry.

Container setup and the matched Commander revision are documented in the Operator
repository under `deploy/dual-arm/README.md` on branch `feat/dual-arm-containers`.
Do not infer physical verification from passing software tests or TCP ACKs.
