import { Canvas } from "@react-three/fiber";
import { Suspense, useEffect, useMemo, useState } from "react";

import { attachPointer } from "@/lib/pointer";
import { Scene } from "./scene/Scene";

export function Experience() {
  const reducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)");

  useEffect(() => {
    const detach = attachPointer();
    return detach;
  }, []);

  const dpr = useMemo(() => {
    if (reducedMotion) return [1, 1] as const;
    const isMobile =
      typeof window !== "undefined" && window.innerWidth < 768;
    if (isMobile) return [1, 1.25] as const;
    return [1, 1.5] as const;
  }, [reducedMotion]);

  return (
    <Canvas
      className="!absolute inset-0"
      dpr={dpr}
      gl={{
        antialias: !reducedMotion,
        powerPreference: reducedMotion ? "default" : "high-performance",
      }}
      camera={{ position: [0, 2.4, 46], fov: 50, near: 0.1, far: 400 }}
    >
      <Suspense fallback={null}>
        <Scene reducedMotion={reducedMotion} />
      </Suspense>
    </Canvas>
  );
}

function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mql = window.matchMedia(query);
    setMatches(mql.matches);
    const onChange = (e: MediaQueryListEvent) => setMatches(e.matches);
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, [query]);

  return matches;
}
