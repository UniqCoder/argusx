import React, { useEffect, useRef, useState } from "react";
import { HeroSection } from "./HeroSection";
import { BlackPanel } from "./BlackPanel";
import { GalleryGrid } from "./GalleryGrid";
import { TraceButton } from "./TraceButton";
import { WhiteOverlay } from "./WhiteOverlay";
import { CustomCursor } from "./CustomCursor";

export const LandingPage: React.FC = () => {
  const [scrollY, setScrollY] = useState(0);
  const [innerTranslateY, setInnerTranslateY] = useState(0);
  const [buttonScale, setButtonScale] = useState(0);
  const [overlayOpacity, setOverlayOpacity] = useState(0);
  const rafRef = useRef<number>();

  useEffect(() => {
    const handleRAF = () => {
      const currentScrollY = window.scrollY;
      setScrollY(currentScrollY);

      const vh = window.innerHeight;
      const maxGalleryScroll = vh * 3; // Gallery grid height minus viewport

      // Phase 1: 0 → vh (GSAP handles BlackPanel slide-up)
      if (currentScrollY <= vh) {
        setInnerTranslateY(0);
        setButtonScale(0);
        setOverlayOpacity(0);
      }
      // Phase 2: vh → vh+maxScroll (gallery scroll)
      else if (currentScrollY <= vh + maxGalleryScroll) {
        const scrollInPhase2 = currentScrollY - vh;
        setInnerTranslateY(-scrollInPhase2);
        setButtonScale(0);
        setOverlayOpacity(0);
      }
      // Phase 3: vh+maxScroll → end (outro)
      else {
        const scrollInPhase3 = currentScrollY - (vh + maxGalleryScroll);
        const maxOutroScroll = vh * 0.5;
        const outroProgress = Math.min(scrollInPhase3 / maxOutroScroll, 1);

        setInnerTranslateY(-maxGalleryScroll); // Lock gallery
        setButtonScale(outroProgress);
        setOverlayOpacity(outroProgress);
      }

      rafRef.current = requestAnimationFrame(handleRAF);
    };

    rafRef.current = requestAnimationFrame(handleRAF);

    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, []);

  const handleButtonClick = () => {
    // Navigate to auth or dashboard
    window.location.href = "/auth";
  };

  // Calculate total scroll height
  const vh = typeof window !== "undefined" ? window.innerHeight : 1000;
  const totalScrollHeight = vh + vh * 3 + vh * 0.5; // hero + gallery + outro

  return (
    <div className="relative bg-[#050810]">
      <CustomCursor />

      {/* Hero Section (fixed, phase 1 background) */}
      <HeroSection />

      {/* Black Panel (slides up in phase 1, scrolls in phase 2) */}
      <BlackPanel innerTranslateY={innerTranslateY}>
        <GalleryGrid innerTranslateY={innerTranslateY} />
      </BlackPanel>

      {/* Outro elements (phase 3) */}
      <TraceButton scale={buttonScale} onClick={handleButtonClick} />
      <WhiteOverlay opacity={overlayOpacity} />

      {/* Spacer to enable scroll */}
      <div style={{ height: `${totalScrollHeight}px` }} />
    </div>
  );
};
