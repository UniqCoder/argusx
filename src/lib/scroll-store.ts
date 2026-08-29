import { useSyncExternalStore } from "react";

type Listener = () => void;

let progress = 0;
let quantized = 0;
const listeners = new Set<Listener>();

export function setScrollProgress(p: number) {
  progress = p;
  // Quantize to 1/200 steps — was 1/500, which triggered ~500 React re-renders
  // per full scroll. 200 steps is visually indistinguishable but cuts DOM
  // re-render frequency by 60%, keeping the main thread free for the RAF loop.
  const q = Math.round(p * 200) / 200;
  if (q !== quantized) {
    quantized = q;
    listeners.forEach((l) => l());
  }
}

/** Raw, un-throttled progress. Safe to read inside useFrame. */
export function getScrollProgress() {
  return progress;
}

function subscribe(listener: Listener) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** Throttled progress for React/DOM layers. */
export function useScrollProgress() {
  return useSyncExternalStore(
    subscribe,
    () => quantized,
    () => 0,
  );
}

/* ---------- shared math ---------- */

export const clamp01 = (v: number) => (v < 0 ? 0 : v > 1 ? 1 : v);

/** normalized 0..1 progress inside the [a,b] window */
export const range = (p: number, a: number, b: number) =>
  clamp01((p - a) / (b - a));

/** smooth 0..1 window with cinematic easing */
export const smoothRange = (p: number, a: number, b: number) => {
  const t = range(p, a, b);
  return t * t * (3 - 2 * t);
};

/** rises in [a,b], holds, falls in [c,d] */
export const band = (p: number, a: number, b: number, c: number, d: number) =>
  smoothRange(p, a, b) * (1 - smoothRange(p, c, d));

export const lerp = (a: number, b: number, t: number) => a + (b - a) * t;

export const easeInOutCubic = (t: number) =>
  t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;

/** frame-rate independent damping */
export const damp = (current: number, target: number, k: number, dt: number) =>
  target + (current - target) * Math.exp(-k * dt);
