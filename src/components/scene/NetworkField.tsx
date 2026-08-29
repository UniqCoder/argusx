import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";

import {
  CLUSTERS,
  LINKS,
  NODE_COUNT,
  clusterOf,
  layoutClusters,
  layoutDeep,
  layoutShell,
  layoutVast,
  nodeSizes,
} from "@/lib/network-data";
import {
  getScrollProgress,
  lerp,
  smoothRange,
  band,
  damp,
} from "@/lib/scroll-store";
import { pointer } from "@/lib/pointer";

const tmp = new THREE.Object3D();
const cA = new THREE.Color();
const cB = new THREE.Color();
const PALE = new THREE.Color("#7fa6d8");
const CYAN = new THREE.Color("#22e0ff");
const clusterColors = CLUSTERS.map((c) => new THREE.Color(c.color));

/** blend the four formations so the network physically re-forms on scroll */
function layoutWeights(p: number) {
  const toShell = smoothRange(p, 0.16, 0.34);
  const toVast = smoothRange(p, 0.56, 0.68);
  const toClusters = smoothRange(p, 0.72, 0.86);
  return [
    (1 - toShell) * (1 - toVast) * (1 - toClusters),
    toShell * (1 - toVast) * (1 - toClusters),
    toVast * (1 - toClusters),
    toClusters,
  ] as const;
}

interface NetworkFieldProps {
  reducedMotion?: boolean;
}

export function NetworkField({ reducedMotion = false }: NetworkFieldProps) {
  const mesh = useRef<THREE.InstancedMesh>(null);
  const lines = useRef<THREE.LineSegments>(null);
  const group = useRef<THREE.Group>(null);
  const px = useRef(0);
  const py = useRef(0);

  const positions = useMemo(() => new Float32Array(NODE_COUNT * 3), []);

  const lineGeo = useMemo(() => {
    const g = new THREE.BufferGeometry();
    g.setAttribute(
      "position",
      new THREE.BufferAttribute(new Float32Array(LINKS.length * 6), 3),
    );
    g.setAttribute(
      "color",
      new THREE.BufferAttribute(new Float32Array(LINKS.length * 6), 3),
    );
    return g;
  }, []);

  useFrame(({ clock }, rawDelta) => {
    const dt = Math.min(rawDelta, 0.05);
    const p = getScrollProgress();
    const t = clock.elapsedTime;
    const [wDeep, wShell, wVast, wClus] = layoutWeights(p);
    const investigate = smoothRange(p, 0.84, 0.95);
    const tronFocus = smoothRange(p, 0.8, 0.92);

    // node positions + colours
    const inst = mesh.current;
    if (!inst) return;
    for (let i = 0; i < NODE_COUNT; i++) {
      const o = i * 3;
      const drift = reducedMotion ? 0 : Math.sin(t * 0.35 + i) * 0.12;
      const x =
        layoutDeep[o]! * wDeep +
        layoutShell[o]! * wShell +
        layoutVast[o]! * wVast +
        layoutClusters[o]! * wClus;
      const y =
        layoutDeep[o + 1]! * wDeep +
        layoutShell[o + 1]! * wShell +
        layoutVast[o + 1]! * wVast +
        layoutClusters[o + 1]! * wClus +
        drift;
      const z =
        layoutDeep[o + 2]! * wDeep +
        layoutShell[o + 2]! * wShell +
        layoutVast[o + 2]! * wVast +
        layoutClusters[o + 2]! * wClus;
      positions[o] = x;
      positions[o + 1] = y;
      positions[o + 2] = z;

      const ci = clusterOf(i);
      const isTron = ci === 2;
      const pulse = reducedMotion ? 1 : 0.75 + Math.sin(t * 2 + i * 0.7) * 0.25;
      let s = nodeSizes[i]! * (1 + wVast * 0.5) * pulse;
      if (isTron) s *= 1 + tronFocus * 0.8;
      tmp.position.set(x, y, z);
      tmp.scale.setScalar(s);
      tmp.updateMatrix();
      inst.setMatrixAt(i, tmp.matrix);

      cA.copy(PALE).lerp(clusterColors[ci]!, wClus * 0.9);
      if (isTron) cA.lerp(CYAN, investigate * 0.85);
      else cA.multiplyScalar(1 - investigate * 0.62);
      inst.setColorAt(i, cA);
    }
    inst.instanceMatrix.needsUpdate = true;
    if (inst.instanceColor) inst.instanceColor.needsUpdate = true;

    // links follow the nodes, disconnecting + reconnecting during transforms
    const lp = lineGeo.getAttribute("position") as THREE.BufferAttribute;
    const lc = lineGeo.getAttribute("color") as THREE.BufferAttribute;
    for (let k = 0; k < LINKS.length; k++) {
      const [a, b] = LINKS[k]!;
      const ao = a * 3;
      const bo = b * 3;
      const o = k * 6;
      lp.array[o] = positions[ao]!;
      lp.array[o + 1] = positions[ao + 1]!;
      lp.array[o + 2] = positions[ao + 2]!;
      lp.array[o + 3] = positions[bo]!;
      lp.array[o + 4] = positions[bo + 1]!;
      lp.array[o + 5] = positions[bo + 2]!;

      const len = Math.hypot(
        positions[ao]! - positions[bo]!,
        positions[ao + 1]! - positions[bo + 1]!,
        positions[ao + 2]! - positions[bo + 2]!,
      );
      // long links fade out — reads as connections breaking and re-forming
      const strength = Math.max(0, 1 - len / (10 + wVast * 22 + wClus * 4));
      const ci = clusterOf(a);
      cB.copy(PALE).lerp(clusterColors[ci]!, wClus * 0.8);
      if (ci === 2) cB.lerp(CYAN, investigate);
      else cB.multiplyScalar(1 - investigate * 0.7);
      cB.multiplyScalar(strength * (reducedMotion ? 0.72 : 0.6 + Math.sin(t + k) * 0.12));
      for (const off of [0, 3]) {
        lc.array[o + off] = cB.r;
        lc.array[o + off + 1] = cB.g;
        lc.array[o + off + 2] = cB.b;
      }
    }
    lp.needsUpdate = true;
    lc.needsUpdate = true;

    // parallax: the whole field counter-moves against the pointer
    if (group.current) {
      const parallaxMul = reducedMotion ? 0.2 : 1;
      px.current = damp(px.current, pointer.x * 1.6 * parallaxMul, 2.5, dt);
      py.current = damp(py.current, pointer.y * 1.1 * parallaxMul, 2.5, dt);
      group.current.position.x = -px.current;
      group.current.position.y = py.current;
      group.current.rotation.y =
        lerp(0, 0.5, smoothRange(p, 0.68, 1)) + px.current * 0.02 * parallaxMul;
      const gone = band(p, 0, 0.02, 0.44, 0.52);
      group.current.visible = true;
      void gone;
    }
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
      <lineSegments ref={lines} geometry={lineGeo} frustumCulled={false}>
        <lineBasicMaterial
          vertexColors
          transparent
          opacity={0.9}
          blending={THREE.AdditiveBlending}
          depthWrite={false}
          toneMapped={false}
        />
      </lineSegments>
    </group>
  );
}
