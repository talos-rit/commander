import geometry from "./armGeometry.json";

export type Vec = [number, number, number];
export type Mat = [Vec, Vec, Vec];
const identity = (): Mat => [[1, 0, 0], [0, 1, 0], [0, 0, 1]];
export const add = (a: Vec, b: Vec): Vec => a.map((v, i) => v + b[i]) as Vec;
export const scale = (a: Vec, s: number): Vec => a.map(v => v * s) as Vec;
const apply = (m: Mat, v: Vec): Vec => m.map(row => row.reduce((s, n, i) => s + n * v[i], 0)) as Vec;
const multiply = (a: Mat, b: Mat): Mat => a.map(row => [0, 1, 2].map(j => row.reduce((s, n, i) => s + n * b[i][j], 0))) as Mat;
function rotation(axis: Vec, angle: number): Mat {
  const [x, y, z] = axis, c = Math.cos(angle), s = Math.sin(angle), t = 1 - c;
  return [[t*x*x+c, t*x*y-s*z, t*x*z+s*y], [t*x*y+s*z, t*y*y+c, t*y*z-s*x], [t*x*z-s*y, t*y*z+s*x, t*z*z+c]];
}

export type LinkPose = { p: Vec; r: Mat };

/** URDF origin (Rz Ry Rx), then joint rotation. Geometry is in metres.
 * armGeometry.json is extracted from digital_twin/sboter4u_model/robots/sboter4u_model.URDF.
 * Returns every link frame in base_Link coordinates; each link's STL mesh is
 * authored in that frame (all URDF visual origins are identity).
 */
export function linkPoses(positions: Record<string, number>): Record<string, LinkPose> {
  const links: Record<string, LinkPose> = { base_Link: { p: [0, 0, 0], r: identity() } };
  for (const joint of geometry) {
    const parent = links[joint.parent];
    const [x, y, z] = joint.rpy;
    const origin = multiply(rotation([0, 0, 1], z), multiply(rotation([0, 1, 0], y), rotation([1, 0, 0], x)));
    const angle = Math.max(joint.lower, Math.min(joint.upper, positions[joint.name] ?? 0));
    const p = add(parent.p, apply(parent.r, joint.xyz as Vec));
    links[joint.child] = { p, r: multiply(multiply(parent.r, origin), rotation(joint.axis as Vec, angle)) };
  }
  return links;
}

/** Joint centres, keyed by joint name, plus a nominal tip for each finger pad. */
export function armPoints(positions: Record<string, number>): Record<string, Vec> {
  const links = linkPoses(positions);
  const points: Record<string, Vec> = {};
  for (const joint of geometry) {
    const { p, r } = links[joint.child];
    points[joint.name] = p;
    if (joint.name.startsWith("pad")) points[`${joint.name}_tip`] = add(p, apply(r, [0.045, 0, 0]));
  }
  return points;
}
