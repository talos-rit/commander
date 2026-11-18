import { lazy, Suspense } from "react";
import type { HostStatus } from "../types";

// three.js and the CAD meshes only load when a twin is actually shown.
const ArmScene = lazy(() => import("./ArmScene"));

export function ArmTwin({ host }: { host?: HostStatus }) {
  const telemetry = host?.telemetry;
  const positions = telemetry?.joint_positions;
  const age = telemetry?.joint_age_s;
  const connected = Boolean(host?.operator_connected);
  const valid = positions && ["shoulder_joint", "elbow_joint", "pitch_joint"].every(name => Number.isFinite(positions[name]));
  const state = !connected ? "Disconnected" : !valid || age == null ? "Waiting for joint telemetry" : age > 1.5 ? "Stale telemetry" : "Live telemetry";
  const pose = valid && connected ? positions : null;
  return <div className="arm-twin">
    <div className="arm-twin__status"><span className={state === "Live telemetry" ? "arm-twin__live" : "muted"}>{state}</span><span className="muted">{age != null && connected ? `${age.toFixed(1)} s` : ""}</span></div>
    <div className="arm-twin__viewport" role="img" aria-label={`Arm visualization: ${state}`}>
      <Suspense fallback={null}><ArmScene positions={pose} dimmed={state === "Stale telemetry"} /></Suspense>
      {!pose && <span className="arm-twin__overlay">No measured pose</span>}
      <span className="arm-twin__caption">100 mm grid · drag to orbit</span>
    </div>
  </div>;
}
