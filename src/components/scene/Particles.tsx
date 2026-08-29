import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";

import { getScrollProgress, lerp, smoothRange } from "@/lib/scroll-store";

const BASE_COUNT = 1400;
const REDUCED_COUNT = 600;

interface ParticlesProps {
  reducedMotion?: boolean;
}

/** Dust / data motes. Depth layer that moves least — the parallax background. */
export function Particles({ reducedMotion = false }: ParticlesProps) {
  const points = useRef<THREE.Points>(null);
  const mat = useRef<THREE.PointsMaterial>(null);

  const geo = useMemo(() => {
    const count = reducedMotion ? REDUCED_COUNT : BASE_COUNT;
    const arr = new Float32Array(count * 3);
    let seed = 91;
    const rnd = () =>
      (seed = (seed * 1664525 + 1013904223) >>> 0) / 4294967296;
    for (let i = 0; i < count; i++) {
      const a = rnd() * Math.PI * 2;
      const r = 4 + Math.pow(rnd(), 0.5) * 60;
      arr[i * 3] = Math.cos(a) * r;
      arr[i * 3 + 1] = (rnd() - 0.5) * 60;
      arr[i * 3 + 2] = Math.sin(a) * r - 10;
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(arr, 3));
    return g;
  }, [reducedMotion]);

  useFrame(({ clock }) => {
    const p = getScrollProgress();
    if (points.current) {
      points.current.rotation.y =
        (reducedMotion ? 0 : clock.elapsedTime * 0.012) + p * 0.9;
      points.current.position.z = lerp(0, 14, p);
    }
    if (mat.current) {
      mat.current.opacity =
        (reducedMotion ? 0.18 : 0.25) + smoothRange(p, 0.4, 0.7) * 0.35;
      mat.current.size = lerp(
        reducedMotion ? 0.06 : 0.07,
        reducedMotion ? 0.11 : 0.13,
        smoothRange(p, 0.4, 0.62),
      );
    }
  });

  return (
    <points ref={points} geometry={geo} frustumCulled={false}>
      <pointsMaterial
        ref={mat}
        color="#9fd8ff"
        size={0.07}
        sizeAttenuation
        transparent
        opacity={0.3}
        depthWrite={false}
        blending={THREE.AdditiveBlending}
        toneMapped={false}
      />
    </points>
  );
}
