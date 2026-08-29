export const pointer = { x: 0, y: 0 };

/**
 * Throttle pointermove to RAF cadence.
 * Raw pointermove fires 60–200×/s on the main thread. We buffer the latest
 * coordinates and only commit them on the next animation frame, so the pointer
 * data and the render loop are always in sync and never race each other.
 */
export function attachPointer() {
  let rafId = 0;
  let nx = 0;
  let ny = 0;

  const onMove = (e: PointerEvent) => {
    nx = (e.clientX / window.innerWidth) * 2 - 1;
    ny = (e.clientY / window.innerHeight) * 2 - 1;
    if (rafId) return; // already have a frame scheduled
    rafId = requestAnimationFrame(() => {
      pointer.x = nx;
      pointer.y = ny;
      rafId = 0;
    });
  };

  window.addEventListener("pointermove", onMove, { passive: true });
  return () => {
    window.removeEventListener("pointermove", onMove);
    if (rafId) cancelAnimationFrame(rafId);
  };
}
