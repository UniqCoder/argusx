import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";

import {
  getScrollProgress,
  band,
  smoothRange,
  lerp,
  damp,
} from "@/lib/scroll-store";
import { pointer } from "@/lib/pointer";
import { createCoinTexture } from "./coin-texture";

/**
 * STATE 02 emergence -> STATE 03 immersion -> STATE 04 camera through object.
 * Everything is derived from scroll progress, so scrolling up rebuilds the
 * exact same states in reverse.
 */
export function BitcoinCoin() {
  const group = useRef<THREE.Group>(null);
  const tilt = useRef<THREE.Group>(null);
  const tex = useMemo(() => createCoinTexture(), []);
  const mats = useRef<THREE.Material[]>([]);
  const mx = useRef(0);
  const my = useRef(0);

  const dataLines = useMemo(() => {
    // engraved circuits peeling off the surface into transaction paths
    const pts: number[] = [];
    let seed = 33;
    const rnd = () => (seed = (seed * 1664525 + 1013904223) >>> 0) / 4294967296;
    for (let i = 0; i < 160; i++) {
      const a = rnd() * Math.PI * 2;
      const r = 0.6 + rnd() * 2.5;
      const x = Math.cos(a) * r;
      const y = Math.sin(a) * r;
      const depth = 2 + rnd() * 16;
      pts.push(x, y, 0.3, x * 1.1, y * 1.1, -depth);
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(pts, 3));
    return g;
  }, []);
  const lineMat = useRef<THREE.LineBasicMaterial>(null);

  useFrame((_, rawDelta) => {
    const dt = Math.min(rawDelta, 0.05);
    const p = getScrollProgress();

    // emergence 0.14 -> 0.34, holds, dissolves once the camera has passed through
    const reveal = smoothRange(p, 0.14, 0.34);
    const dissolve = smoothRange(p, 0.5, 0.6);
    const scale =
      lerp(0.3, 1, reveal) * lerp(1, 1.35, smoothRange(p, 0.34, 0.5));
    const opacity = reveal * (1 - dissolve);

    if (group.current) {
      group.current.scale.setScalar(scale);
      group.current.visible = opacity > 0.002;
      group.current.position.z = lerp(-16, 0, reveal);
      group.current.rotation.z += dt * 0.12;
    }
    if (tilt.current) {
      mx.current = damp(mx.current, pointer.x * 0.18, 3, dt);
      my.current = damp(my.current, pointer.y * 0.14, 3, dt);
      tilt.current.rotation.y = mx.current + Math.sin(p * 6) * 0.08;
      tilt.current.rotation.x = -my.current;
    }
    for (const m of mats.current) {
      m.opacity = opacity;
      m.transparent = opacity < 0.999;
    }
    if (lineMat.current) {
      lineMat.current.opacity = band(p, 0.42, 0.5, 0.62, 0.72) * 0.7;
    }
  });

  return (
    <group ref={group}>
      <group ref={tilt}>
        <mesh rotation-x={Math.PI / 2} castShadow>
          <cylinderGeometry args={[3.2, 3.2, 0.52, 96, 1, false]} />
          <meshStandardMaterial
            ref={(m) => {
              if (m) mats.current[0] = m;
            }}
            color="#c98d21"
            metalness={1}
            roughness={0.28}
            emissive="#42260a"
            emissiveIntensity={0.35}
          />
        </mesh>
        {[0.27, -0.27].map((z, i) => (
          <mesh key={z} position-z={z} rotation-y={i === 1 ? Math.PI : 0}>
            <circleGeometry args={[3.18, 96]} />
            <meshStandardMaterial
              ref={(m) => {
                if (m) mats.current[1 + i] = m;
              }}
              map={tex}
              emissiveMap={tex}
              emissive="#ffb64a"
              emissiveIntensity={0.35}
              metalness={0.95}
              roughness={0.32}
            />
          </mesh>
        ))}
        <lineSegments geometry={dataLines}>
          <lineBasicMaterial
            ref={lineMat}
            color="#ffcb6b"
            transparent
            opacity={0}
            blending={THREE.AdditiveBlending}
            depthWrite={false}
            toneMapped={false}
          />
        </lineSegments>
      </group>
    </group>
  );
}
