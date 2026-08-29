import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";

import {
  CLEAN_COUNT,
  FRAUD_COUNT,
  LINK_COUNT,
  LINKS,
  NODE_COUNT,
  nodeSizes,
  shatterVelocities,
  spherePositions,
} from "@/lib/shatter-data";
import { getScrollProgress, smoothRange, lerp, damp } from "@/lib/scroll-store";

const tmp = new THREE.Object3D();
const cClean = new THREE.Color("#7ab8ff"); // blue-white: clean nodes
const cFraud = new THREE.Color("#ff3b5c"); // red: fraud nodes
const cFaded = new THREE.Color("#1a2a44"); // near-invisible: faded clean nodes

/**
 * ACT 1 (0–0.30): Perfect sphere, slowly rotating. All nodes blue-white.
 * ACT 2 (0.30–0.60): Shatter — nodes fly outward from their sphere positions.
 *   Clean nodes fade out during the explosion.
 *   Fraud nodes stay bright red throughout.
 * ACT 3 (0.60–1.00): Clean nodes gone. Fraud nodes hand off to FraudCluster.
 *   This component fades out entirely by 0.70.
 */
export function SphereField() {
  const mesh = useRef<THREE.InstancedMesh>(null);
  const lines = useRef<THREE.LineSegments>(null);
  const group = useRef<THREE.Group>(null);
  const rotY = useRef(0);

  // Pre-allocate working arrays
  const curPos = useMemo(() => new Float32Array(spherePositions), []); // mutable copy
  const lineBuf = useMemo(() => {
    const g = new THREE.BufferGeometry();
    g.setAttribute(
      "position",
      new THREE.BufferAttribute(new Float32Array(LINK_COUNT * 6), 3),
    );
    g.setAttribute(
      "color",
      new THREE.BufferAttribute(new Float32Array(LINK_COUNT * 6), 3),
    );
    return g;
  }, []);

  useFrame((_, rawDelta) => {
    const dt = Math.min(rawDelta, 0.05);
    const p = getScrollProgress();

    // ── scroll windows ──
    const shatter = smoothRange(p, 0.28, 0.58); // 0→1 during explosion
    const fadeOut = smoothRange(p, 0.6, 0.72); // whole component fades
    const groupAlpha = 1 - fadeOut;
    if (!group.current) return;
    group.current.visible = groupAlpha > 0.005;

    // Slow rotation in Act 1, stops as shatter begins
    rotY.current += dt * 0.09 * (1 - shatter);
    group.current.rotation.y = rotY.current;

    const inst = mesh.current;
    if (!inst) return;

    // Eased shatter curve — slow start, fast middle, gentle end
    const sq = shatter * shatter * (3 - 2 * shatter); // smoothstep already applied via smoothRange

    // ── update each node ──
    for (let i = 0; i < NODE_COUNT; i++) {
      const o = i * 3;
      const isFraud = i < FRAUD_COUNT;

      // position: sphere → scattered
      const sx = spherePositions[o]!;
      const sy = spherePositions[o + 1]!;
      const sz = spherePositions[o + 2]!;
      const vx = shatterVelocities[o]!;
      const vy = shatterVelocities[o + 1]!;
      const vz = shatterVelocities[o + 2]!;

      const x = sx + vx * sq;
      const y = sy + vy * sq;
      const z = sz + vz * sq;
      curPos[o] = x;
      curPos[o + 1] = y;
      curPos[o + 2] = z;

      // scale
      const pulse = 0.8 + Math.sin(Date.now() * 0.001 + i * 0.4) * 0.2;
      const s = nodeSizes[i]! * pulse * (1 + (isFraud ? shatter * 0.6 : 0));

      tmp.position.set(x, y, z);
      tmp.scale.setScalar(s);
      tmp.updateMatrix();
      inst.setMatrixAt(i, tmp.matrix);

      // colour
      let col: THREE.Color;
      if (isFraud) {
        col = cFraud;
      } else {
        // clean nodes fade to near-invisible during shatter
        const cleanFade = smoothRange(shatter, 0.3, 0.85);
        col = cClean.clone().lerp(cFaded, cleanFade);
      }
      // apply group alpha
      const a = groupAlpha;
      inst.setColorAt(i, col.clone().multiplyScalar(a));
    }
    inst.instanceMatrix.needsUpdate = true;
    if (inst.instanceColor) inst.instanceColor.needsUpdate = true;

    // ── link lines ──
    const lp = lineBuf.getAttribute("position") as THREE.BufferAttribute;
    const lc = lineBuf.getAttribute("color") as THREE.BufferAttribute;
    for (let k = 0; k < LINK_COUNT; k++) {
      const [a, b] = LINKS[k]!;
      const ao = a * 3,
        bo = b * 3,
        o = k * 6;
      lp.array[o] = curPos[ao]!;
      lp.array[o + 1] = curPos[ao + 1]!;
      lp.array[o + 2] = curPos[ao + 2]!;
      lp.array[o + 3] = curPos[bo]!;
      lp.array[o + 4] = curPos[bo + 1]!;
      lp.array[o + 5] = curPos[bo + 2]!;

      const len = Math.hypot(
        curPos[ao]! - curPos[bo]!,
        curPos[ao + 1]! - curPos[bo + 1]!,
        curPos[ao + 2]! - curPos[bo + 2]!,
      );
      const isFraudLink = a < FRAUD_COUNT && b < FRAUD_COUNT;
      const strength =
        Math.max(0, 1 - len / (isFraudLink ? 14 : 10)) *
        groupAlpha *
        (1 - smoothRange(shatter, 0.2, 0.7));
      const r = isFraudLink ? 1.0 * strength : 0.48 * strength;
      const g = isFraudLink ? 0.23 * strength : 0.72 * strength;
      const bv = isFraudLink ? 0.36 * strength : 1.0 * strength;
      for (const off of [0, 3]) {
        lc.array[o + off] = r;
        lc.array[o + off + 1] = g;
        lc.array[o + off + 2] = bv;
      }
    }
    lp.needsUpdate = true;
    lc.needsUpdate = true;
  });

  return (
    <group ref={group}>
      <instancedMesh
        ref={mesh}
        args={[undefined, undefined, NODE_COUNT]}
        frustumCulled={false}
      >
        <icosahedronGeometry args={[1, 1]} />
        <meshBasicMaterial toneMapped={false} />
      </instancedMesh>
      <lineSegments ref={lines} geometry={lineBuf} frustumCulled={false}>
        <lineBasicMaterial
          vertexColors
          transparent
          opacity={0.85}
          blending={THREE.AdditiveBlending}
          depthWrite={false}
          toneMapped={false}
        />
      </lineSegments>
    </group>
  );
}
