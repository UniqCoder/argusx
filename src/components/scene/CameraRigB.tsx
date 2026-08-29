import { useFrame } from "@react-three/fiber";
import { useRef } from "react";
import * as THREE from "three";

import {
  damp,
  easeInOutCubic,
  getScrollProgress,
  lerp,
} from "@/lib/scroll-store";
import { pointer } from "@/lib/pointer";

/**
 * Camera timeline for the Shatter+Reconstruct experience.
 *
 * ACT 1  0.00–0.28  Wide orbit of the sphere — shows its scale
 * ACT 2  0.28–0.62  Falls toward the explosion — "inside the shatter"
 * ACT 3  0.62–1.00  Pulls back slightly, then pushes into the fraud cluster
 */

type Key = {
  p: number;
  pos: [number, number, number];
  look: [number, number, number];
};

const KEYS: Key[] = [
  // ACT 1 — orbital wide shots
  { p: 0.0, pos: [0, 4, 58], look: [0, 0, 0] }, // very wide — full sphere visible
  { p: 0.12, pos: [22, 6, 46], look: [0, 0, 0] }, // slight orbit right
  { p: 0.22, pos: [-10, 8, 42], look: [0, 0, 0] }, // swing left

  // ACT 2 — falling into explosion
  { p: 0.3, pos: [0, 2, 32], look: [0, 0, 0] }, // start descent
  { p: 0.42, pos: [0, 0, 12], look: [0, 0, 0] }, // inside the burst
  { p: 0.54, pos: [2, -2, -4], look: [0, 0, -8] }, // through the debris

  // ACT 3 — re-orient to fraud cluster (offset +4x, -2z from origin)
  { p: 0.62, pos: [10, 6, 20], look: [4, 0, -2] }, // pull back, reframe
  { p: 0.72, pos: [14, 4, 14], look: [4, 0, -2] }, // orbit the cluster
  { p: 0.82, pos: [8, 2, 10], look: [4, 0, -2] }, // tighten
  { p: 0.91, pos: [6, 1, 6], look: [4, 0, -2] }, // push in close
  { p: 1.0, pos: [5, 0.5, 4], look: [4, 0, -2] }, // maximum intimacy
];

const pos = new THREE.Vector3();
const look = new THREE.Vector3();

export function CameraRigB() {
  const cur = useRef(new THREE.Vector3(0, 4, 58));
  const tgt = useRef(new THREE.Vector3(0, 0, 0));
  const mx = useRef(0);
  const my = useRef(0);

  useFrame(({ camera }, rawDelta) => {
    const dt = Math.min(rawDelta, 0.05);
    const p = getScrollProgress();

    // Find bracketing keyframes
    let i = 0;
    while (i < KEYS.length - 2 && p > KEYS[i + 1]!.p) i++;
    const a = KEYS[i]!;
    const b = KEYS[i + 1]!;
    const t = easeInOutCubic(Math.min(1, Math.max(0, (p - a.p) / (b.p - a.p))));

    pos.set(
      lerp(a.pos[0], b.pos[0], t),
      lerp(a.pos[1], b.pos[1], t),
      lerp(a.pos[2], b.pos[2], t),
    );
    look.set(
      lerp(a.look[0], b.look[0], t),
      lerp(a.look[1], b.look[1], t),
      lerp(a.look[2], b.look[2], t),
    );

    // Pointer parallax — subtle, more muted during the explosion
    const explosionIntensity = Math.max(0, 1 - Math.abs(p - 0.45) * 8);
    const pointerScale = lerp(1.0, 0.3, explosionIntensity);
    mx.current = damp(mx.current, pointer.x * 1.4 * pointerScale, 1.8, dt);
    my.current = damp(my.current, pointer.y * 0.9 * pointerScale, 1.8, dt);
    pos.x += mx.current;
    pos.y -= my.current;

    // Smooth damp to target
    cur.current.x = damp(cur.current.x, pos.x, 3.5, dt);
    cur.current.y = damp(cur.current.y, pos.y, 3.5, dt);
    cur.current.z = damp(cur.current.z, pos.z, 3.5, dt);
    tgt.current.x = damp(tgt.current.x, look.x, 3.2, dt);
    tgt.current.y = damp(tgt.current.y, look.y, 3.2, dt);
    tgt.current.z = damp(tgt.current.z, look.z, 3.2, dt);

    camera.position.copy(cur.current);
    camera.lookAt(tgt.current);
  });

  return null;
}
