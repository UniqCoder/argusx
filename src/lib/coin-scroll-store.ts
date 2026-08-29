import { useSyncExternalStore } from "react";

type Listener = () => void;
let progress = 0;
let quantized = 0;
const listeners = new Set<Listener>();

export function setCoinProgress(p: number) {
  progress = p;
  const q = Math.round(p * 200) / 200;
  if (q !== quantized) {
    quantized = q;
    listeners.forEach((l) => l());
  }
}

export function getCoinProgress() {
  return progress;
}

function subscribe(l: Listener) {
  listeners.add(l);
  return () => listeners.delete(l);
}

export function useCoinProgress() {
  return useSyncExternalStore(
    subscribe,
    () => quantized,
    () => 0,
  );
}
