import { Canvas, useFrame } from "@react-three/fiber";
import { Suspense, useMemo, useRef } from "react";
import * as THREE from "three";
import { createCoinTexture } from "@/components/scene/coin-texture";

/* ─── Slow-spinning coin (self-contained, no scroll dependency) ─── */
function SpinningCoin() {
  const group = useRef<THREE.Group>(null);
  const tilt = useRef<THREE.Group>(null);
  const mats = useRef<THREE.Material[]>([]);
  const tex = useMemo(() => createCoinTexture(), []);

  const dataLines = useMemo(() => {
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

  useFrame((_, dt) => {
    if (group.current) group.current.rotation.z += dt * 0.18;
    if (tilt.current) {
      tilt.current.rotation.y += dt * 0.22;
      tilt.current.rotation.x = Math.sin(Date.now() * 0.0004) * 0.18;
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
              emissiveIntensity={0.4}
              metalness={0.95}
              roughness={0.32}
            />
          </mesh>
        ))}
        <lineSegments geometry={dataLines}>
          <lineBasicMaterial
            color="#ffcb6b"
            transparent
            opacity={0.45}
            blending={THREE.AdditiveBlending}
            depthWrite={false}
            toneMapped={false}
          />
        </lineSegments>
      </group>
    </group>
  );
}

/* ─── Ambient particle dust ─── */
function AuthParticles() {
  const ref = useRef<THREE.Points>(null);
  const geo = useMemo(() => {
    const arr = new Float32Array(600 * 3);
    let seed = 77;
    const rnd = () => (seed = (seed * 1664525 + 1013904223) >>> 0) / 4294967296;
    for (let i = 0; i < 600; i++) {
      const a = rnd() * Math.PI * 2;
      const r = 5 + Math.pow(rnd(), 0.5) * 28;
      arr[i * 3] = Math.cos(a) * r;
      arr[i * 3 + 1] = (rnd() - 0.5) * 28;
      arr[i * 3 + 2] = Math.sin(a) * r - 8;
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(arr, 3));
    return g;
  }, []);

  useFrame(({ clock }) => {
    if (ref.current) ref.current.rotation.y = clock.elapsedTime * 0.014;
  });

  return (
    <points ref={ref} geometry={geo} frustumCulled={false}>
      <pointsMaterial
        color="#9fd8ff"
        size={0.09}
        sizeAttenuation
        transparent
        opacity={0.28}
        depthWrite={false}
        blending={THREE.AdditiveBlending}
        toneMapped={false}
      />
    </points>
  );
}

/* ─── USP data for overlay cards ─── */
const USPS = [
  {
    icon: "⚡",
    label: "Real-time chokepoint",
    value: "Stop funds before cash-out · <200ms",
  },
  {
    icon: "🔗",
    label: "Cross-victim correlation",
    value: "Same wallet, multiple victims? Instant freeze signal.",
  },
  {
    icon: "🔒",
    label: "100% data sovereign",
    value: "FIR narratives never leave your infrastructure.",
  },
];

/* ─── Full AuthScene component ─── */
export function AuthScene() {
  return (
    <div className="auth-scene">
      {/* 3-D canvas */}
      <Canvas
        className="!absolute inset-0"
        dpr={[1, 1.6]}
        gl={{ antialias: true, powerPreference: "high-performance" }}
        camera={{ position: [0, 1.2, 14], fov: 50, near: 0.1, far: 200 }}
      >
        <color attach="background" args={["#04060c"]} />
        <fog attach="fog" args={["#04060c", 28, 120]} />
        <ambientLight intensity={0.4} />
        <directionalLight
          position={[8, 12, 10]}
          intensity={2.2}
          color="#ffd9a0"
        />
        <directionalLight
          position={[-10, -4, -8]}
          intensity={0.9}
          color="#3ba7ff"
        />
        <pointLight
          position={[0, 0, 6]}
          intensity={20}
          distance={28}
          color="#ffb64a"
        />
        <Suspense fallback={null}>
          <AuthParticles />
          <SpinningCoin />
        </Suspense>
      </Canvas>

      {/* vignette */}
      <div className="auth-scene__vignette" />

      {/* headline */}
      <div className="auth-scene__headline">
        <p className="auth-scene__kicker">
          <span className="beat__index">ARGUS</span>
          Blockchain Intelligence
        </p>
        <h2 className="auth-scene__title">
          Follow the money.
          <br />
          Stop the crime.
        </h2>
      </div>

      {/* USP cards — anchored to bottom of the right panel */}
      <div className="auth-scene__usps">
        {USPS.map((u) => (
          <div key={u.label} className="auth-usp">
            <span className="auth-usp__icon">{u.icon}</span>
            <div>
              <p className="annotation__label">{u.label}</p>
              <p className="annotation__value">{u.value}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
