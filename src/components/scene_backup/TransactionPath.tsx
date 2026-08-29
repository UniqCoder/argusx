import { Html } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useMemo, useRef, useState } from "react";
import * as THREE from "three";

import { TRON_PATH } from "@/lib/network-data";
import {
  band,
  clamp01,
  getScrollProgress,
  range,
  smoothRange,
} from "@/lib/scroll-store";

/** STATE 07 — a single transaction physically travelling wallet to wallet. */
export function TransactionPath() {
  const group = useRef<THREE.Group>(null);
  const pulse = useRef<THREE.Mesh>(null);
  const trail = useRef<THREE.LineSegments>(null);
  const mat = useRef<THREE.LineBasicMaterial>(null);
  const walletMats = useRef<THREE.MeshBasicMaterial[]>([]);
  const [visible, setVisible] = useState(false);

  const curve = useMemo(
    () =>
      new THREE.CatmullRomCurve3(TRON_PATH.map((p) => new THREE.Vector3(...p))),
    [],
  );

  const pathGeo = useMemo(() => {
    const pts = curve.getPoints(160);
    const arr: number[] = [];
    for (let i = 0; i < pts.length - 1; i++) {
      arr.push(
        pts[i]!.x,
        pts[i]!.y,
        pts[i]!.z,
        pts[i + 1]!.x,
        pts[i + 1]!.y,
        pts[i + 1]!.z,
      );
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(arr, 3));
    return g;
  }, [curve]);

  useFrame(({ clock }) => {
    const p = getScrollProgress();
    const on = band(p, 0.78, 0.86, 1.01, 1.02);
    const show = on > 0.01;
    if (show !== visible) setVisible(show);
    if (mat.current) mat.current.opacity = on;

    // the transaction travels as the user scrolls: scroll IS the timeline
    const travel = clamp01(range(p, 0.84, 0.97));
    if (pulse.current) {
      const pos = curve.getPointAt(travel * 0.999);
      pulse.current.position.copy(pos);
      const s = 0.28 + Math.sin(clock.elapsedTime * 5) * 0.05;
      pulse.current.scale.setScalar(s * on);
    }
    walletMats.current.forEach((m, i) => {
      const reached = clamp01((travel - i / (TRON_PATH.length - 1)) * 6);
      m.opacity = on * (0.35 + reached * 0.65);
    });
    if (trail.current) trail.current.visible = show;
    if (group.current) group.current.visible = show;
    void smoothRange;
  });

  return (
    <group ref={group} visible={false}>
      <lineSegments ref={trail} geometry={pathGeo}>
        <lineBasicMaterial
          ref={mat}
          color="#22e0ff"
          transparent
          opacity={0}
          blending={THREE.AdditiveBlending}
          depthWrite={false}
          toneMapped={false}
        />
      </lineSegments>

      <mesh ref={pulse}>
        <sphereGeometry args={[1, 24, 24]} />
        <meshBasicMaterial color="#d8fbff" toneMapped={false} />
      </mesh>

      {TRON_PATH.map((p, i) => (
        <mesh key={i} position={p}>
          <icosahedronGeometry
            args={[i === TRON_PATH.length - 1 ? 0.55 : 0.36, 2]}
          />
          <meshBasicMaterial
            ref={(m) => {
              if (m) walletMats.current[i] = m;
            }}
            color={i === TRON_PATH.length - 1 ? "#ff3b5c" : "#22e0ff"}
            transparent
            opacity={0}
            toneMapped={false}
          />
        </mesh>
      ))}

      {/* STATE 08 — annotations spatially anchored to the suspicious cluster */}
      {visible && (
        <>
          <Html
            position={[-20.5, -1.5, -9]}
            center
            distanceFactor={16}
            zIndexRange={[20, 10]}
          >
            <div className="annotation annotation--alert">
              <span className="annotation__dot" />
              <div>
                <p className="annotation__label">Risk signal detected</p>
                <p className="annotation__value">
                  Destination flagged · 0x9f…c41d
                </p>
              </div>
            </div>
          </Html>
          <Html
            position={[-14.5, 1.4, -1]}
            center
            distanceFactor={18}
            zIndexRange={[20, 10]}
          >
            <div className="annotation">
              <p className="annotation__label">High-volume path</p>
              <p className="annotation__value">4 hops · 1.42M USDT · TRON</p>
            </div>
          </Html>
          <Html
            position={[-16.5, -6.6, -7]}
            center
            distanceFactor={18}
            zIndexRange={[20, 10]}
          >
            <div className="annotation">
              <p className="annotation__label">Multiple intermediate wallets</p>
              <p className="annotation__value">
                Layering pattern · 92% confidence
              </p>
            </div>
          </Html>
        </>
      )}
    </group>
  );
}
