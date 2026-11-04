# Web arm visualization

The Debug rail's Digital twin section renders a fixed orthographic view of the
selected robot. It has no pointer interaction or command path. Shaded boxes use
the URDF joint centres, including the two 0.22 m arm links. Body thicknesses and
finger tips are simplified visual geometry rather than CAD dimensions.

`src/armGeometry.json` records the joint origin, RPY, axis, and limits from
`../digital_twin/sboter4u_model/robots/sboter4u_model.URDF`. Keep it synchronized
when changing that model. `armKinematics.ts` applies URDF origin transforms before
joint rotations and clamps the displayed joint angles as the desktop viewer does.
The simplified pedestal needs no CAD mesh leveling correction.

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
