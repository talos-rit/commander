import { useEffect, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";
import { toCreasedNormals } from "three/examples/jsm/utils/BufferGeometryUtils.js";
import { linkPoses } from "../armKinematics";
import baseUrl from "../../../digital_twin/sboter4u_model/meshes/base_Link.STL?url";
import shoulderUrl from "../../../digital_twin/sboter4u_model/meshes/shoulder_Link.STL?url";
import elbowUrl from "../../../digital_twin/sboter4u_model/meshes/elbow_Link.STL?url";
import pitchUrl from "../../../digital_twin/sboter4u_model/meshes/pitch_Link.STL?url";
import rollUrl from "../../../digital_twin/sboter4u_model/meshes/roll_Link.STL?url";
import gripperUrl from "../../../digital_twin/sboter4u_model/meshes/gripper_Link.STL?url";
import pad1Url from "../../../digital_twin/sboter4u_model/meshes/pad1_Link.STL?url";
import pad2Url from "../../../digital_twin/sboter4u_model/meshes/pad2_Link.STL?url";

// Same meshes the PyBullet viewer loads from sboter4u_model.URDF.
const LINKS: { name: string; url: string; color: number; metalness?: number; roughness?: number }[] = [
  { name: "base_Link", url: baseUrl, color: 0x2a3138, roughness: 0.7 },
  { name: "shoulder_Link", url: shoulderUrl, color: 0x2563c9 },
  { name: "elbow_Link", url: elbowUrl, color: 0x3174dd },
  { name: "pitch_Link", url: pitchUrl, color: 0x2563c9 },
  { name: "roll_Link", url: rollUrl, color: 0x6b7a86, metalness: 0.5 },
  { name: "gripper_Link", url: gripperUrl, color: 0x47525c, metalness: 0.4 },
  { name: "pad1_Link", url: pad1Url, color: 0xc8483c },
  { name: "pad2_Link", url: pad2Url, color: 0xc8483c },
];

// The CAD base mesh is tilted in its own frame; mirror the desktop viewer's
// LEGACY_MODEL_LEVEL_RPY (src/simulation/viewer.py) so the pedestal sits level.
const LEVEL_RPY: [number, number, number] = [-0.0629868471, 0.0040045985, 0];

// Shared across mounts so switching robots doesn't refetch or reprocess meshes.
let geometries: Promise<Record<string, THREE.BufferGeometry>> | null = null;
function loadGeometries() {
  geometries ??= Promise.all(LINKS.map(async ({ name, url }) => {
    const raw = await new STLLoader().loadAsync(url);
    raw.deleteAttribute("normal");
    // Smooth curved surfaces while keeping CAD edges crisp.
    return [name, toCreasedNormals(raw, Math.PI / 6)] as const;
  })).then(Object.fromEntries).catch(error => { geometries = null; throw error; });
  return geometries;
}

function setPose(object: THREE.Object3D, pose: { p: number[]; r: number[][] }) {
  const [[a, b, c], [d, e, f], [g, h, i]] = pose.r;
  object.matrix.set(a, b, c, pose.p[0], d, e, f, pose.p[1], g, h, i, pose.p[2], 0, 0, 0, 1);
  object.matrixWorldNeedsUpdate = true;
}

export type ArmSceneProps = {
  /** URDF joint radians, or null to show the empty cell. */
  positions: Record<string, number> | null;
  dimmed: boolean;
};

export default function ArmScene({ positions, dimmed }: ArmSceneProps) {
  const host = useRef<HTMLDivElement>(null);
  const api = useRef<{ pose: (p: Record<string, number> | null) => void; dim: (d: boolean) => void } | null>(null);
  const latest = useRef({ positions, dimmed });
  latest.current = { positions, dimmed };

  useEffect(() => {
    const container = host.current!;
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    } catch {
      container.dataset.unavailable = "true";
      return;
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    container.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(32, 1, 0.01, 20);
    camera.up.set(0, 0, 1);
    const target = new THREE.Vector3(0, 0, 0.44);
    camera.position.set(1.85, 0.74, 1.0);

    scene.add(new THREE.HemisphereLight(0xdfe9f3, 0x1a232b, 1.1));
    const key = new THREE.DirectionalLight(0xffffff, 2.2);
    key.position.set(1.2, 0.8, 2.0);
    key.castShadow = true;
    key.shadow.mapSize.set(1024, 1024);
    key.shadow.camera.left = key.shadow.camera.bottom = -0.8;
    key.shadow.camera.right = key.shadow.camera.top = 0.8;
    key.shadow.radius = 4;
    key.shadow.bias = -0.0005;
    scene.add(key);
    const rim = new THREE.DirectionalLight(0x9ec9ff, 0.9);
    rim.position.set(-1.5, -1.0, 1.2);
    scene.add(rim);

    const grid = new THREE.GridHelper(1.0, 10, 0x4b6070, 0x2c3b47);
    grid.rotation.x = Math.PI / 2;
    (grid.material as THREE.Material).transparent = true;
    (grid.material as THREE.Material).opacity = 0.6;
    scene.add(grid);
    const floor = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), new THREE.ShadowMaterial({ opacity: 0.35 }));
    floor.receiveShadow = true;
    floor.position.z = -0.0005;
    scene.add(floor);

    // world <- level/centre correction <- base_Link frame
    const robot = new THREE.Group();
    const model = new THREE.Group();
    model.rotation.set(...LEVEL_RPY, "ZYX");
    robot.add(model);
    robot.visible = false;
    scene.add(robot);

    const materials = LINKS.map(({ color, metalness = 0.15, roughness = 0.45 }) =>
      new THREE.MeshStandardMaterial({ color, metalness, roughness }));
    const parts: Record<string, THREE.Mesh> = {};

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.target.copy(target);
    controls.enablePan = false;
    controls.minDistance = 0.8;
    controls.maxDistance = 4;
    controls.maxPolarAngle = Math.PI * 0.49;

    let frame = 0;
    const render = () => {
      frame ||= requestAnimationFrame(() => { frame = 0; renderer.render(scene, camera); });
    };
    controls.addEventListener("change", render);
    renderer.domElement.addEventListener("dblclick", () => { controls.reset(); render(); });
    controls.update();
    controls.saveState();

    const resize = () => {
      const { width } = container.getBoundingClientRect();
      if (!width) return;
      const height = width * 0.85;
      renderer.setSize(width, height);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      render();
    };
    const observer = new ResizeObserver(resize);
    observer.observe(container);
    resize();

    api.current = {
      pose: next => {
        robot.visible = Boolean(next) && Object.keys(parts).length > 0;
        if (next) {
          const poses = linkPoses(next);
          for (const [name, mesh] of Object.entries(parts)) setPose(mesh, poses[name]);
        }
        render();
      },
      dim: d => {
        for (const m of materials) Object.assign(m, { transparent: d, opacity: d ? 0.4 : 1, needsUpdate: true });
        render();
      },
    };

    let disposed = false;
    loadGeometries().then(geoms => {
      if (disposed) return;
      LINKS.forEach(({ name }, i) => {
        const mesh = new THREE.Mesh(geoms[name], materials[i]);
        mesh.matrixAutoUpdate = false;
        mesh.castShadow = mesh.receiveShadow = true;
        parts[name] = mesh;
        model.add(mesh);
      });
      // Sit the levelled pedestal on the floor, centred under the base joint.
      setPose(parts.base_Link, linkPoses({}).base_Link);
      robot.updateMatrixWorld(true);
      const box = new THREE.Box3().setFromObject(parts.base_Link);
      const axis = new THREE.Vector3(...linkPoses({}).shoulder_Link.p).applyMatrix4(model.matrixWorld);
      robot.position.set(-axis.x, -axis.y, -box.min.z);
      api.current?.pose(latest.current.positions);
      api.current?.dim(latest.current.dimmed);
    }).catch(() => { container.dataset.unavailable = "true"; });

    return () => {
      disposed = true;
      api.current = null;
      cancelAnimationFrame(frame);
      observer.disconnect();
      controls.dispose();
      materials.forEach(m => m.dispose());
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, []);

  useEffect(() => { api.current?.pose(positions); }, [positions]);
  useEffect(() => { api.current?.dim(dimmed); }, [dimmed]);

  return <div ref={host} className="arm-twin__scene" title="Drag to orbit · scroll to zoom · double-click to reset" />;
}
