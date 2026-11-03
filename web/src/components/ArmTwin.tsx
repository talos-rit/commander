import type { HostStatus } from "../types";
import { add, armPoints, depth, project, scale, type Vec } from "../armKinematics";

function beam(a: Vec, b: Vec, width: number, color: string, key: string) {
  const delta = add(b, scale(a, -1));
  const length = Math.hypot(...delta);
  const direction = scale(delta, 1 / (length || 1));
  const helper: Vec = Math.abs(direction[2]) < 0.9 ? [0, 0, 1] : [0, 1, 0];
  const cross = (u: Vec, v: Vec): Vec => [u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0]];
  const raw = cross(direction, helper);
  const u = scale(raw, width / Math.hypot(...raw));
  const v = scale(cross(direction, u), 1);
  const corners = [a, b].flatMap(p => [[1, 1], [-1, 1], [-1, -1], [1, -1]].map(([i, j]) => add(p, add(scale(u, i), scale(v, j)))));
  return [[0, 1, 2, 3], [4, 5, 6, 7], [0, 4, 5, 1], [1, 5, 6, 2], [2, 6, 7, 3], [3, 7, 4, 0]]
    .map((indices, i) => ({ points: indices.map(n => corners[n]), i }))
    .sort((a, b) => depth(scale(a.points.reduce(add), 0.25)) - depth(scale(b.points.reduce(add), 0.25)))
    .map(({ points, i }) => <polygon key={`${key}-${i}`} points={points.map(p => project(p).join(",")).join(" ")} fill={color} stroke="#142431" strokeWidth="0.6" style={{ filter: `brightness(${0.65 + i * 0.09})` }} />);
}

export function ArmTwin({ host }: { host?: HostStatus }) {
  const telemetry = host?.telemetry;
  const positions = telemetry?.joint_positions;
  const age = telemetry?.joint_age_s;
  const connected = Boolean(host?.operator_connected);
  const valid = positions && ["shoulder_joint", "elbow_joint", "pitch_joint"].every(name => Number.isFinite(positions[name]));
  const state = !connected ? "Disconnected" : !valid || age == null ? "Waiting for joint telemetry" : age > 1.5 ? "Stale telemetry" : "Live telemetry";
  const p = valid && connected ? armPoints(positions) : null;
  const segments: [Vec, Vec, number, string][] = p ? [
    [[0.13222, -0.16175, 0.025], p.base_joint, 0.065, "#526572"],
    [p.base_joint, p.shoulder_joint, 0.047, "#526572"],
    [p.shoulder_joint, p.elbow_joint, 0.030, "#49a4d8"],
    [p.elbow_joint, p.pitch_joint, 0.025, "#49a4d8"],
    [p.pitch_joint, p.pad1_joint, 0.018, "#8799a5"],
    [p.pitch_joint, p.pad2_joint, 0.018, "#8799a5"],
    [p.pad1_joint, p.pad1_joint_tip, 0.009, "#b8c6cf"],
    [p.pad2_joint, p.pad2_joint_tip, 0.009, "#b8c6cf"],
  ] : [];
  return <div className="arm-twin">
    <div className="arm-twin__status"><span className={state === "Live telemetry" ? "arm-twin__live" : "muted"}>{state}</span><span className="muted">{age != null && connected ? `${age.toFixed(1)} s` : ""}</span></div>
    <svg viewBox="0 0 320 285" role="img" aria-label={`Fixed camera arm visualization: ${state}`}>
      <ellipse cx="160" cy="255" rx="95" ry="20" fill="#101b24" />
      {Array.from({ length: 9 }, (_, i) => {
        const t = (i - 4) * 0.1;
        return <g key={i} stroke="#344552" strokeWidth="0.6" opacity="0.5">
          <line x1={project([t + .13222, -.56, 0])[0]} y1={project([t + .13222, -.56, 0])[1]} x2={project([t + .13222, .24, 0])[0]} y2={project([t + .13222, .24, 0])[1]} />
          <line x1={project([-.27, t - .16175, 0])[0]} y1={project([-.27, t - .16175, 0])[1]} x2={project([.53, t - .16175, 0])[0]} y2={project([.53, t - .16175, 0])[1]} />
        </g>;
      })}
      <g opacity={state === "Stale telemetry" ? 0.45 : 1}>
        {segments.sort((a, b) => depth(add(a[0], a[1])) - depth(add(b[0], b[1]))).map(([a, b, w, c], i) => <g key={i}>{beam(a, b, w, c, String(i))}</g>)}
      </g>
      {!p && <text x="160" y="140" textAnchor="middle" fill="#99aab6" fontSize="12">No measured pose</text>}
      <text x="12" y="275" fill="#99aab6" fontSize="10">100 mm grid · fixed camera</text>
    </svg>
    <p className="hint">Measured arm pose. {positions?.base_joint == null ? "Base yaw unavailable. " : "Base yaw reference unverified. "}Roll and gripper shown in a fixed pose.</p>
  </div>;
}
