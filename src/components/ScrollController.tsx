import { useEffect } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

import { setScrollProgress } from "@/lib/scroll-store";

gsap.registerPlugin(ScrollTrigger);

/**
 * ONE controller. GSAP ScrollTrigger pins the 3D stage and publishes a single
 * scroll progress value; camera, coin, network, particles, wallets and text all
 * read from it, so the same scroll position always produces the same state.
 *
 * scrub: 0.25 — lerps input over ~250ms. Smooths wheel-event bursts without
 * making the first scroll gesture feel sluggish (0.4 was too heavy on the
 * initial phase-01 → phase-02 transition).
 */
export function ScrollController() {
  useEffect(() => {
    const st = ScrollTrigger.create({
      trigger: "#story",
      start: "top top",
      end: "bottom bottom",
      pin: "#stage",
      pinSpacing: false,
      scrub: 0.25,
      onUpdate: (self) => setScrollProgress(self.progress),
      onRefresh: (self) => setScrollProgress(self.progress),
    });
    return () => st.kill();
  }, []);

  return null;
}
