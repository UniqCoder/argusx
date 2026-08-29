import { Environment, Lightformer } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";

import { createCoinTexture } from "@/components/scene/coin-texture";
import { getCoinProgress } from "@/lib/coin-scroll-store";
import { damp, lerp, smoothRange, band } from "@/lib/scroll-store";
import { pointer } from "@/lib/pointer";

function BitcoinCoin() {
  const group = useRef<THREE.Group>(null);
  const tilt = useRef<THREE.Group>(null);
  const tex = useMemo(() => createCoinTexture(), []);
  const mats = useRef<THREE.Material[]>([]);
  const mx = useRef(0);
  const my = useRef(0);

  // Data lines geometry -- circuits peeling off the coin face
  const dataLines = useMemo(() => {
    const pts: number[] = [];
    let seed = 33;
    const rnd = () => (seed = (seed * 1664525 + 1013904223) >>> 0) / 4294967296;
    for (let i = 0; i < 160; i++) {
      const a = rnd() * Math.PI * 2;
      const r = 0.6 + rnd() * 2.5;
      pts.push(
        Math.cos(a) * r,
        Math.sin(a) * r,
        0.3,
        Math.cos(a) * r * 1.1,
        Math.sin(a) * r * 1.1,
        -(2 + rnd() * 16),
      );
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(pts, 3));
    return g;
  }, []);
  const lineMat = useRef<THREE.LineBasicMaterial>(null);

  useFrame((_, rawDelta) => {
    const dt = Math.min(rawDelta, 0.05);
    const p = getCoinProgress();

    // Rise in: 0.05 -> 0.35  |  hold: 0.35 -> 0.70  |  dissolve out: 0.78 -> 0.95
    const reveal = smoothRange(p, 0.05, 0.35);
    const dissolve = smoothRange(p, 0.78, 0.95);
    const scale =
      lerp(0.3, 1, reveal) * lerp(1, 1.2, smoothRange(p, 0.35, 0.6));
    const opacity = reveal * (1 - dissolve);

    if (group.current) {
      group.current.visible = opacity > 0.002;
      group.current.scale.setScalar(scale);
      group.current.position.z = lerp(-18, 0, reveal);
      group.current.rotation.z += dt * 0.1;
    }
    if (tilt.current) {
      mx.current = damp(mx.current, pointer.x * 0.22, 3, dt);
      my.current = damp(my.current, pointer.y * 0.16, 3, dt);
      tilt.current.rotation.y = mx.current;
      tilt.current.rotation.x = -my.current;
    }
    mats.current.forEach((m) => {
      (m as THREE.MeshStandardMaterial).opacity = opacity;
      m.transparent = opacity < 0.999;
    });
    if (lineMat.current) {
      // Data lines appear during the hold phase
      lineMat.current.opacity = band(p, 0.4, 0.55, 0.7, 0.82) * 0.75;
    }
  });

  return (
    <group ref={group}>
      <group ref={tilt}>
        {/* Coin body */}
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
        {/* Front and back faces with texture */}
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
        {/* Data lines peeling off */}
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

// Simple camera: pulls back smoothly as the coin enters, then holds
function CoinCamera() {
  const cur = useRef(new THREE.Vector3(0, 0, 22));
  const tgt = useRef(new THREE.Vector3(0, 0, 0));
  const mx = useRef(0);
  const my = useRef(0);

  useFrame(({ camera }, rawDelta) => {
    const dt = Math.min(rawDelta, 0.05);
    const p = getCoinProgress();

    // Camera starts far, eases in to a comfortable viewing distance
    const z = lerp(22, 10, smoothRange(p, 0.0, 0.4));
    const y = lerp(0, 1.5, smoothRange(p, 0.1, 0.5));

    mx.current = damp(mx.current, pointer.x * 1.0, 1.8, dt);
    my.current = damp(my.current, pointer.y * 0.6, 1.8, dt);

    cur.current.x = damp(cur.current.x, mx.current, 3.5, dt);
    cur.current.y = damp(cur.current.y, y - my.current, 3.5, dt);
    cur.current.z = damp(cur.current.z, z, 3.5, dt);
    tgt.current.x = damp(tgt.current.x, 0, 3.2, dt);
    tgt.current.y = damp(tgt.current.y, 0, 3.2, dt);
    tgt.current.z = damp(tgt.current.z, 0, 3.2, dt);

    camera.position.copy(cur.current);
    camera.lookAt(tgt.current);
  });
  return null;
}

export function CoinScene() {
  return (
    <>
      <color attach="background" args={["#04060c"]} />
      <fog attach="fog" args={["#04060c", 30, 120]} />

      <ambientLight intensity={0.35} />
      <directionalLight
        position={[8, 12, 10]}
        intensity={2.1}
        color="#ffd9a0"
      />
      <directionalLight
        position={[-10, -4, -8]}
        intensity={0.9}
        color="#3ba7ff"
      />
      <pointLight
        position={[0, 0, 6]}
        intensity={22}
        distance={30}
        color="#ffb64a"
      />

      <Environment resolution={128}>
        <Lightformer
          intensity={2.4}
          position={[0, 6, 4]}
          scale={[12, 12, 1]}
          color="#fff0d4"
        />
        <Lightformer
          intensity={1.4}
          color="#3ba7ff"
          position={[-8, 0, 2]}
          rotation-y={Math.PI / 2}
          scale={[22, 6, 1]}
        />
        <Lightformer
          intensity={1.1}
          color="#22e0ff"
          position={[8, -2, -2]}
          rotation-y={-Math.PI / 2}
          scale={[22, 6, 1]}
        />
      </Environment>

      <CoinCamera />
      <BitcoinCoin />
    </>
  );
}
