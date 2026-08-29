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

type Key = {
  p: number;
  pos: [number, number, number];
  look: [number, number, number];
};

/** The single deterministic camera timeline. scrollProgress -> camera state. */
const KEYS: Key[] = [
  { p: 0.0, pos: [0, 2.4, 46], look: [0, 0, 0] }, // 01 network discovery
  { p: 0.12, pos: [0, 1.6, 30], look: [0, 0, 0] },
  { p: 0.28, pos: [0, 1.0, 16], look: [0, 0, 0] }, // 02 bitcoin emergence
  { p: 0.42, pos: [1.6, 0.6, 8.4], look: [0, 0, 0] }, // 03 immersion
  { p: 0.5, pos: [0.5, 0.2, 4.4], look: [0, 0, -2] },
  { p: 0.58, pos: [0, 0, -2.6], look: [0, 0, -12] }, // 04 through the object
  { p: 0.64, pos: [0, 1.5, -16], look: [0, 0, -6] },
  { p: 0.72, pos: [4, 6, -44], look: [0, 0, -6] }, // 05 expanding universe
  { p: 0.8, pos: [26, 10, -50], look: [2, 0, -6] }, // 06 multi-chain orbit
  { p: 0.88, pos: [-6, 2, -30], look: [-16, -2, -4] }, // 07 tron path
  { p: 0.94, pos: [-24, 0.5, -22], look: [-16, -3, -5] },
  { p: 1.0, pos: [-29, 4, -15], look: [-16, -4, -6] }, // 08 investigation orbit
];

const pos = new THREE.Vector3();
const look = new THREE.Vector3();

export function CameraRig() {
  const cur = useRef(new THREE.Vector3(0, 2.4, 46));
  const tgt = useRef(new THREE.Vector3(0, 0, 0));
  const mx = useRef(0);
  const my = useRef(0);

  useFrame(({ camera }, rawDelta) => {
    const dt = Math.min(rawDelta, 0.05);
    const p = getScrollProgress();

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

    // Mouse parallax with inertia.
    // k reduced from 2.2 → 1.8 so pointer lag feels intentional, not broken.
    mx.current = damp(mx.current, pointer.x * 1.2, 1.8, dt);
    my.current = damp(my.current, pointer.y * 0.8, 1.8, dt);
    pos.x += mx.current;
    pos.y -= my.current;

    // Position damp: k reduced 6 → 4.5 — removes micro-judder on fast scroll
    // while keeping the camera feeling responsive at normal scroll pace.
    cur.current.x = damp(cur.current.x, pos.x, 4.5, dt);
    cur.current.y = damp(cur.current.y, pos.y, 4.5, dt);
    cur.current.z = damp(cur.current.z, pos.z, 4.5, dt);

    // Look-at damp: k reduced 5 → 4 for the same reason.
    tgt.current.x = damp(tgt.current.x, look.x, 4, dt);
    tgt.current.y = damp(tgt.current.y, look.y, 4, dt);
    tgt.current.z = damp(tgt.current.z, look.z, 4, dt);

    camera.position.copy(cur.current);
    camera.lookAt(tgt.current);
  });

  return null;
}
