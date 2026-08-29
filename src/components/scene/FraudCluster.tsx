import { Html } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useMemo, useRef, useState } from "react";
import * as THREE from "three";

import {
  FRAUD_COUNT,
  fraudRestPositions,
  nodeSizes,
  shatterVelocities,
  spherePositions,
} from "@/lib/shatter-data";
import { damp, getScrollProgress, smoothRange } from "@/lib/scroll-store";

const cFraud = new THREE.Color("#ff3b5c");
const cHot = new THREE.Color("#ff8c00");
const cAnnote = new THREE.Color("#22e0ff");
const tmp = new THREE.Object3D();

/**
 * ACT 3 — The fraud cluster.
 *
 * scroll 0.55–0.72: Nodes materialise from scattered positions (carried over
 *   from SphereField's shatter state) and magnetically snap to their rest
 *   positions in a tight blob.
 * scroll 0.72–1.00: Cluster fully formed. Slow internal pulse. Annotation
 *   cards appear. Camera pushes in.
 */
export function FraudCluster() {
  const mesh = useRef<THREE.InstancedMesh>(null);
  const group = useRef<THREE.Group>(null);
  const [annotationsVisible, setAnnotationsVisible] = useState(false);

  // Scattered start: same positions as where SphereField left the fraud nodes
  const scatteredPos = useMemo(() => {
    const arr = new Float32Array(FRAUD_COUNT * 3);
    for (let i = 0; i < FRAUD_COUNT; i++) {
      const o = i * 3;
      const sq = 1; // fully scattered (end of explosion)
      arr[o] = spherePositions[o]! + shatterVelocities[o]! * sq;
      arr[o + 1] = spherePositions[o + 1]! + shatterVelocities[o + 1]! * sq;
      arr[o + 2] = spherePositions[o + 2]! + shatterVelocities[o + 2]! * sq;
    }
    return arr;
  }, []);

  // Damped current positions for silky magnetic snap
  const curPos = useRef(new Float32Array(scatteredPos));

  useFrame((_, rawDelta) => {
    const dt = Math.min(rawDelta, 0.05);
    const p = getScrollProgress();

    // Component fades in during 0.55–0.68
    const fadeIn = smoothRange(p, 0.55, 0.68);
    // Magnetic snap: nodes travel to rest positions 0.62–0.82
    const snap = smoothRange(p, 0.62, 0.82);
    // Internal pulse after fully formed
    const pulse = smoothRange(p, 0.8, 0.92);

    if (!group.current) return;
    group.current.visible = fadeIn > 0.005;

    // Show HTML annotations once cluster is mostly formed
    const shouldAnnotate = snap > 0.7;
    if (shouldAnnotate !== annotationsVisible)
      setAnnotationsVisible(shouldAnnotate);

    const inst = mesh.current;
    if (!inst) return;

    const t = Date.now() * 0.001;

    for (let i = 0; i < FRAUD_COUNT; i++) {
      const o = i * 3;

      // Target: lerp between scattered and rest based on snap progress
      const tx =
        scatteredPos[o]! + (fraudRestPositions[o]! - scatteredPos[o]!) * snap;
      const ty =
        scatteredPos[o + 1]! +
        (fraudRestPositions[o + 1]! - scatteredPos[o + 1]!) * snap;
      const tz =
        scatteredPos[o + 2]! +
        (fraudRestPositions[o + 2]! - scatteredPos[o + 2]!) * snap;

      // Smooth damp for organic magnetic feel — k=5 is snappy but not instant
      curPos.current[o] = damp(curPos.current[o]!, tx, 5, dt);
      curPos.current[o + 1] = damp(curPos.current[o + 1]!, ty, 5, dt);
      curPos.current[o + 2] = damp(curPos.current[o + 2]!, tz, 5, dt);

      const x = curPos.current[o]!;
      const y = curPos.current[o + 1]!;
      const z = curPos.current[o + 2]!;

      // Pulsing scale after cluster is formed
      const pulseFactor = 1 + pulse * Math.sin(t * 2.2 + i * 0.35) * 0.18;
      const s = nodeSizes[i]! * 1.4 * pulseFactor * fadeIn;

      tmp.position.set(x, y, z);
      tmp.scale.setScalar(s);
      tmp.updateMatrix();
      inst.setMatrixAt(i, tmp.matrix);

      // Colour: red → hot orange as cluster pulses
      const col = cFraud
        .clone()
        .lerp(cHot, pulse * (0.4 + Math.sin(t * 1.8 + i) * 0.3));
      col.multiplyScalar(fadeIn);
      inst.setColorAt(i, col);
    }
    inst.instanceMatrix.needsUpdate = true;
    if (inst.instanceColor) inst.instanceColor.needsUpdate = true;

    // Slow cluster rotation once formed
    if (group.current) {
      group.current.rotation.y += dt * 0.06 * pulse;
    }
  });

  return (
    <group ref={group} visible={false}>
      <instancedMesh
        ref={mesh}
        args={[undefined, undefined, FRAUD_COUNT]}
        frustumCulled={false}
      >
        <icosahedronGeometry args={[1, 2]} />
        <meshBasicMaterial toneMapped={false} />
      </instancedMesh>

      {annotationsVisible && (
        <>
          <Html
            position={[8, 4, 0]}
            center
            distanceFactor={18}
            zIndexRange={[30, 20]}
          >
            <div className="annotation annotation--alert">
              <span className="annotation__dot" />
              <div>
                <p className="annotation__label">High-risk cluster</p>
                <p className="annotation__value">
                  220 flagged wallets · 3 exchanges
                </p>
              </div>
            </div>
          </Html>

          <Html
            position={[-2, -5, 3]}
            center
            distanceFactor={18}
            zIndexRange={[30, 20]}
          >
            <div className="annotation">
              <div>
                <p className="annotation__label">Cross-victim correlation</p>
                <p className="annotation__value">47 FIRs · ₹12.4 Cr at risk</p>
              </div>
            </div>
          </Html>

          <Html
            position={[6, -3, -4]}
            center
            distanceFactor={18}
            zIndexRange={[30, 20]}
          >
            <div className="annotation">
              <div>
                <p className="annotation__label">Nearest VASP identified</p>
                <p className="annotation__value">
                  Binance · Deposit chokepoint
                </p>
              </div>
            </div>
          </Html>

          <Html
            position={[-5, 3, -2]}
            center
            distanceFactor={18}
            zIndexRange={[30, 20]}
          >
            <div className="annotation">
              <div>
                <p className="annotation__label">Risk score</p>
                <p className="annotation__value">
                  0.94 critical · Freeze recommended
                </p>
              </div>
            </div>
          </Html>
        </>
      )}
    </group>
  );
}
