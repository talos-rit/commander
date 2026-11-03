import geometry from "./armGeometry.json";

export type Vec = [number, number, number];
type Mat = [Vec, Vec, Vec];
const identity = (): Mat => [[1, 0, 0], [0, 1, 0], [0, 0, 1]];
export const add = (a: Vec, b: Vec): Vec => a.map((v, i) => v + b[i]) as Vec;
export const scale = (a: Vec, s: number): Vec => a.map(v => v * s) as Vec;
const apply = (m: Mat, v: Vec): Vec => m.map(row => row.reduce((s, n, i) => s + n * v[i], 0)) as Vec;
const multiply = (a: Mat, b: Mat): Mat => a.map(row => [0, 1, 2].map(j => row.reduce((s, n, i) => s + n * b[i][j], 0))) as Mat;
function rotation(axis: Vec, angle: number): Mat {
  const [x, y, z] = axis, c = Math.cos(angle), s = Math.sin(angle), t = 1 - c;
  return [[t*x*x+c, t*x*y-s*z, t*x*z+s*y], [t*x*y+s*z, t*y*y+c, t*y*z-s*x], [t*x*z-s*y, t*y*z+s*x, t*z*z+c]];
}

/** URDF origin (Rz Ry Rx), then joint rotation. Geometry is in metres.
 * armGeometry.json is extracted from digital_twin/sboter4u_model/robots/sboter4u_model.URDF.
 * This simplified model uses joint centres rather than the tilted CAD meshes.
 */
export function armPoints(positions: Record<string, number>): Record<string, Vec> {
  const links: Record<string, { p: Vec; r: Mat }> = { base_Link: { p: [0, 0, 0], r: identity() } };
  const points: Record<string, Vec> = {};
  for (const joint of geometry) {
    const parent = links[joint.parent];
    const [x, y, z] = joint.rpy;
    const origin = multiply(rotation([0, 0, 1], z), multiply(rotation([0, 1, 0], y), rotation([1, 0, 0], x)));
    const angle = Math.max(joint.lower, Math.min(joint.upper, positions[joint.name] ?? 0));
    const p = add(parent.p, apply(parent.r, joint.xyz as Vec));
    const r = multiply(multiply(parent.r, origin), rotation(joint.axis as Vec, angle));
    links[joint.child] = { p, r };
    points[joint.name] = p;
    if (joint.name.startsWith("pad")) points[`${joint.name}_tip`] = add(p, apply(r, [0.045, 0, 0]));
  }
  return points;
}

/** Fixed orthographic camera, with enough room for the entire arm envelope. */
export function project([x, y, z]: Vec): [number, number] {
  x -= 0.13222; y += 0.16175;
  return [160 + 225 * (0.82*x - 0.57*y), 255 - 225 * (z + 0.26*x + 0.37*y)];
}
export const depth = ([x, y, z]: Vec) => 0.57*x + 0.82*y - 0.4*z;
