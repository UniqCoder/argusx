import { useEffect, useRef } from "react";

/** Desktop-only neon cursor ring. Hidden on touch devices via CSS. */
export function CustomCursor() {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    let rafId = 0;
    let cx = -100,
      cy = -100;

    const onMove = (e: MouseEvent) => {
      cx = e.clientX;
      cy = e.clientY;
      if (rafId) return;
      rafId = requestAnimationFrame(() => {
        el.style.left = `${cx}px`;
        el.style.top = `${cy}px`;
        rafId = 0;
      });
    };
    window.addEventListener("mousemove", onMove, { passive: true });
    return () => {
      window.removeEventListener("mousemove", onMove);
      if (rafId) cancelAnimationFrame(rafId);
    };
  }, []);

  return (
    <div ref={ref} className="ug-cursor" aria-hidden="true">
      <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
        <circle cx="24" cy="24" r="22.75" stroke="#f5a524" strokeWidth="2" />
        {/* Stylised chain-link glyph inside the ring */}
        <path
          d="M18 24h4m8 0h-4m-4 0v-4m0 4v4"
          stroke="#f5a524"
          strokeWidth="1.5"
          strokeLinecap="round"
        />
        <circle cx="24" cy="24" r="2" fill="#f5a524" />
      </svg>
    </div>
  );
}
