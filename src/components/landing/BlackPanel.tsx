import React, { useRef, useEffect } from "react";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

interface BlackPanelProps {
  innerTranslateY: number;
  children: React.ReactNode;
}

export const BlackPanel: React.FC<BlackPanelProps> = ({
  innerTranslateY,
  children,
}) => {
  const panelRef = useRef<HTMLDivElement>(null);
  const innerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!panelRef.current) return;

    // GSAP slide up animation (phase 1)
    const tl = gsap.timeline({
      scrollTrigger: {
        trigger: panelRef.current,
        start: "top bottom",
        end: "top top",
        scrub: 1,
        markers: false,
      },
    });

    tl.fromTo(panelRef.current, { y: "100vh" }, { y: "0vh", ease: "none" });

    return () => {
      ScrollTrigger.getAll().forEach((trigger) => trigger.kill());
    };
  }, []);

  // RAF-driven inner translateY (phase 2)
  useEffect(() => {
    if (innerRef.current) {
      innerRef.current.style.transform = `translateY(${innerTranslateY}px)`;
    }
  }, [innerTranslateY]);

  return (
    <div
      ref={panelRef}
      className="fixed inset-0 bg-[#050810] z-10"
      style={{ transform: "translateY(100vh)" }}
    >
      <div ref={innerRef} className="w-full h-full">
        {children}
      </div>
    </div>
  );
};
