import React, { useState, useEffect, useCallback } from "react";
import { HeroLeft } from "./HeroLeft";
import { HeroRight } from "./HeroRight";
import { HeroOverlay } from "./HeroOverlay";

interface HeroSectionProps {
  className?: string;
}

export const HeroSection: React.FC<HeroSectionProps> = ({ className = "" }) => {
  const [mouseX, setMouseX] = useState(0); // -1 to 1
  const [mouseY, setMouseY] = useState(0); // -1 to 1
  const [leftOpacity, setLeftOpacity] = useState(1);
  const [rightOpacity, setRightOpacity] = useState(0.3);

  const handleMouseMove = useCallback((e: MouseEvent) => {
    const x = (e.clientX / window.innerWidth) * 2 - 1;
    const y = -((e.clientY / window.innerHeight) * 2 - 1);

    setMouseX(x);
    setMouseY(y);

    // Deadzone logic: X < -0.2 = left foreground, X > 0.2 = right foreground
    if (x < -0.2) {
      setLeftOpacity(1);
      setRightOpacity(0.3);
    } else if (x > 0.2) {
      setLeftOpacity(0.3);
      setRightOpacity(1);
    } else {
      // Neutral zone - both visible
      const blend = (x + 0.2) / 0.4; // 0 to 1 across neutral zone
      setLeftOpacity(1 - blend * 0.7);
      setRightOpacity(0.3 + blend * 0.7);
    }
  }, []);

  useEffect(() => {
    window.addEventListener("mousemove", handleMouseMove);
    return () => window.removeEventListener("mousemove", handleMouseMove);
  }, [handleMouseMove]);

  return (
    <div
      className={`relative w-full h-screen bg-[#050810] overflow-hidden ${className}`}
    >
      {/* Left panel - fraud stats */}
      <div className="absolute inset-0 bg-gradient-to-r from-[#050810] via-[#050810]/50 to-transparent">
        <HeroLeft opacity={leftOpacity} />
      </div>

      {/* Right panel - 3D Bitcoin */}
      <div className="absolute inset-0 bg-gradient-to-l from-[#050810] via-[#050810]/50 to-transparent">
        <HeroRight opacity={rightOpacity} mouseX={mouseX} mouseY={mouseY} />
      </div>

      {/* Fixed overlays */}
      <HeroOverlay />
    </div>
  );
};
