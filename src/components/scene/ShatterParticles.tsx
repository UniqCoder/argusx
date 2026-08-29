import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";

import { getScrollProgress, smoothRange } from "@/lib/scroll-store";

const COUNT = 2200; // fine debris fragments

/**
 * Fast-moving debris that flies TOWARD the camera during the explosion
 * (scroll 0.32 – 0.62). Creates the "camera inside the explosion" feel.
 * Uses a simple Points geometry — very cheap to render.
 */
export function ShatterParticles() {
  const ref = useRef<THREE.Points>(null);
  const mat = useRef<THREE.PointsMaterial>(null);

  const { positions, velocities } = useMemo(() => {
    // Deterministic RNG
    let seed = 55123;
    const rnd = () => {
      seed = (seed * 1664525 + 1013904223) >>> 0;
      return seed / 4294967296;
    };

    const positions = new Float32Array(COUNT * 3);
    const velocities = new Float32Array(COUNT * 3); // x,y,z velocity toward camera (+z)

    for (let i = 0; i < COUNT; i++) {
      // Start clustered in a sphere around origin
      const phi = Math.acos(2 * rnd() - 1);
      const theta = rnd() * Math.PI * 2;
      const r = 3 + rnd() * 16;
      positions[i * 3] = Math.sin(phi) * Math.cos(theta) * r;
      positions[i * 3 + 1] = Math.sin(phi) * Math.sin(theta) * r * 0.8;
      positions[i * 3 + 2] = Math.cos(phi) * r;

      // Velocity: mostly toward camera (+z) with lateral spread
      velocities[i * 3] = (rnd() - 0.5) * 24;
      velocities[i * 3 + 1] = (rnd() - 0.5) * 16;
      velocities[i * 3 + 2] = 18 + rnd() * 36; // strongly toward camera
    }
    return { positions, velocities };
  }, []);

  const geo = useMemo(() => {
    const g = new THREE.BufferGeometry();
    g.setAttribute(
      "position",
      new THREE.BufferAttribute(new Float32Array(positions), 3),
    );
    return g;
  }, [positions]);

  const curPos = useMemo(() => new Float32Array(positions), [positions]);

  useFrame(() => {
    const p = getScrollProgress();
    const burst = smoothRange(p, 0.3, 0.62); // 0→1 during explosion
    const fade = smoothRange(p, 0.55, 0.7); // fade out after peak
    const alpha = burst * (1 - fade);

    if (!ref.current || !mat.current) return;
    mat.current.opacity = alpha * 0.75;
    ref.current.visible = alpha > 0.005;
    if (!ref.current.visible) return;

    const sq = burst * burst * (3 - 2 * burst); // smoothstep
    const pos = geo.getAttribute("position") as THREE.BufferAttribute;

    for (let i = 0; i < COUNT; i++) {
      const o = i * 3;
      curPos[o] = positions[o]! + velocities[o]! * sq;
      curPos[o + 1] = positions[o + 1]! + velocities[o + 1]! * sq;
      curPos[o + 2] = positions[o + 2]! + velocities[o + 2]! * sq;
      pos.array[o] = curPos[o]!;
      pos.array[o + 1] = curPos[o + 1]!;
      pos.array[o + 2] = curPos[o + 2]!;
    }
    pos.needsUpdate = true;
  });

  return (
    <points ref={ref} geometry={geo} frustumCulled={false}>
      <pointsMaterial
        ref={mat}
        color="#88ccff"
        size={0.12}
        sizeAttenuation
        transparent
        opacity={0}
        depthWrite={false}
        blending={THREE.AdditiveBlending}
        toneMapped={false}
      />
    </points>
  );
}
