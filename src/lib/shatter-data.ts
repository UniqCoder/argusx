/**
 * Deterministic data for the Shatter+Reconstruct experience.
 * All RNG is seeded so every reload / scroll-reverse gives identical positions.
 */

export const NODE_COUNT = 1800; // total nodes in the sphere
export const FRAUD_COUNT = 220; // nodes that survive as the fraud cluster
export const CLEAN_COUNT = NODE_COUNT - FRAUD_COUNT;

/* ── deterministic LCG ── */
function rng(seed: number) {
  let s = seed >>> 0;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 4294967296;
  };
}

/* ── sphere surface positions (Fibonacci lattice — even distribution) ── */
export const spherePositions = new Float32Array(NODE_COUNT * 3);
{
  const golden = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < NODE_COUNT; i++) {
    const y = 1 - (i / (NODE_COUNT - 1)) * 2;
    const r = Math.sqrt(1 - y * y);
    const phi = golden * i;
    const R = 18; // sphere radius
    spherePositions[i * 3] = Math.cos(phi) * r * R;
    spherePositions[i * 3 + 1] = y * R;
    spherePositions[i * 3 + 2] = Math.sin(phi) * r * R;
  }
}

/* ── shatter velocities — each node explodes outward + random spin ── */
export const shatterVelocities = new Float32Array(NODE_COUNT * 3);
{
  const r = rng(77331);
  for (let i = 0; i < NODE_COUNT; i++) {
    // base: outward from sphere center (normalised position × speed)
    const ox = spherePositions[i * 3]!;
    const oy = spherePositions[i * 3 + 1]!;
    const oz = spherePositions[i * 3 + 2]!;
    const len = Math.sqrt(ox * ox + oy * oy + oz * oz) || 1;
    const speed = 28 + r() * 22; // 28–50 units of travel
    shatterVelocities[i * 3] = (ox / len) * speed + (r() - 0.5) * 12;
    shatterVelocities[i * 3 + 1] = (oy / len) * speed + (r() - 0.5) * 12;
    shatterVelocities[i * 3 + 2] = (oz / len) * speed + (r() - 0.5) * 8;
  }
}

/* ── fraud cluster: tight irregular blob, offset to right-center of scene ── */
export const fraudRestPositions = new Float32Array(FRAUD_COUNT * 3);
{
  const r = rng(9913);
  for (let i = 0; i < FRAUD_COUNT; i++) {
    // Gaussian-ish cluster via Box-Muller
    const u1 = Math.max(1e-6, r());
    const u2 = r();
    const mag = Math.sqrt(-2 * Math.log(u1)) * 4.5; // spread 4.5
    const ang = 2 * Math.PI * u2;
    const u3 = Math.max(1e-6, r());
    const u4 = r();
    const mag2 = Math.sqrt(-2 * Math.log(u3)) * 4.5;
    const ang2 = 2 * Math.PI * u4;
    fraudRestPositions[i * 3] = Math.cos(ang) * mag + 4; // +4 x offset
    fraudRestPositions[i * 3 + 1] = Math.cos(ang2) * mag2 * 0.7; // flatter y
    fraudRestPositions[i * 3 + 2] = Math.sin(ang) * mag - 2; // -2 z offset
  }
}

/* ── node sizes ── */
export const nodeSizes = new Float32Array(NODE_COUNT);
{
  const r = rng(4421);
  for (let i = 0; i < NODE_COUNT; i++) {
    nodeSizes[i] = 0.06 + r() * 0.14;
  }
}

/* ── link pairs for sphere (short-range, stable across layouts) ── */
export const LINK_COUNT = 1200;
export const LINKS: Array<[number, number]> = Array.from(
  { length: LINK_COUNT },
  (_, k) => {
    const a = (k * 7) % NODE_COUNT;
    const b = (a + 3 + (k % 4)) % NODE_COUNT;
    return [a, b];
  },
);
