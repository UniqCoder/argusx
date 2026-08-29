/**
 * Deterministic node layouts for the blockchain network.
 * Every layout holds the SAME node count so the network can physically
 * re-form between scroll states instead of being replaced.
 */

export const NODE_COUNT = 420;
export const LINK_COUNT = 520;

/** deterministic pseudo random so every reload / scroll direction matches */
function rng(seed: number) {
  let s = seed >>> 0;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 4294967296;
  };
}

const r = rng(20260827);
const seeds = Array.from({ length: NODE_COUNT * 4 }, () => r());
const s = (i: number, k: number) => seeds[(i * 4 + k) % seeds.length] as number;

export type Layout = Float32Array;

function make(fn: (i: number) => [number, number, number]): Layout {
  const arr = new Float32Array(NODE_COUNT * 3);
  for (let i = 0; i < NODE_COUNT; i++) {
    const [x, y, z] = fn(i);
    arr[i * 3] = x;
    arr[i * 3 + 1] = y;
    arr[i * 3 + 2] = z;
  }
  return arr;
}

/** STATE 01 — deep corridor of nodes, strong z distribution for parallax */
export const layoutDeep = make((i) => {
  const a = s(i, 0) * Math.PI * 2;
  const rad = 7 + s(i, 1) * 26;
  const z = -40 + s(i, 2) * 78;
  return [Math.cos(a) * rad, Math.sin(a) * rad * 0.6, z];
});

/** STATE 02/03 — shell wrapping the coin */
export const layoutShell = make((i) => {
  const u = s(i, 0);
  const v = s(i, 1);
  const phi = Math.acos(2 * u - 1);
  const theta = v * Math.PI * 2;
  const rad = 8.5 + s(i, 2) * 5;
  return [
    Math.sin(phi) * Math.cos(theta) * rad,
    Math.sin(phi) * Math.sin(theta) * rad * 0.8,
    Math.cos(phi) * rad,
  ];
});

/** STATE 05 — enormous expanding universe */
export const layoutVast = make((i) => {
  const a = s(i, 0) * Math.PI * 2;
  const rad = 6 + Math.pow(s(i, 1), 0.6) * 44;
  const y = (s(i, 2) - 0.5) * 34;
  return [Math.cos(a) * rad, y, Math.sin(a) * rad - 6];
});

/** STATE 06/07/08 — four chain clusters */
export const CLUSTERS = [
  { name: "BITCOIN", center: [16, 5, -10] as const, color: "#f5a524" },
  { name: "ETHEREUM", center: [4, -8, 4] as const, color: "#8fa2c9" },
  { name: "TRON", center: [-16, -2, -4] as const, color: "#ff3b5c" },
  { name: "USDT", center: [-6, 9, -16] as const, color: "#3ad6a4" },
];

export const clusterOf = (i: number) => i % CLUSTERS.length;

export const layoutClusters = make((i) => {
  const c = CLUSTERS[clusterOf(i)]!.center;
  const a = s(i, 0) * Math.PI * 2;
  const b = Math.acos(2 * s(i, 1) - 1);
  const rad = 1.5 + Math.pow(s(i, 2), 0.7) * 7.5;
  return [
    c[0] + Math.sin(b) * Math.cos(a) * rad,
    c[1] + Math.sin(b) * Math.sin(a) * rad,
    c[2] + Math.cos(b) * rad,
  ];
});

/** stable link pairs — kept short-range in index space so lines survive every layout */
export const LINKS: Array<[number, number]> = Array.from(
  { length: LINK_COUNT },
  (_, k) => {
    const a = (k * 7) % NODE_COUNT;
    const b = (a + 4 + Math.floor(s(k, 3) * 5) * 4) % NODE_COUNT;
    return [a, b] as [number, number];
  },
);

/** wallets of the followed TRON transaction path (in cluster space) */
export const TRON_PATH: Array<[number, number, number]> = [
  [-11.5, 1.5, 2.5],
  [-14.5, -1.0, -1.0],
  [-18.0, -3.5, -3.0],
  [-15.5, -5.5, -7.0],
  [-20.5, -1.5, -9.0],
];

export const nodeSizes = Float32Array.from(
  { length: NODE_COUNT },
  (_, i) => 0.085 + s(i, 3) * 0.17,
);
