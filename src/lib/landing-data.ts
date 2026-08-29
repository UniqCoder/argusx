/** ─── Fraud counter stats shown in HeroLeft ─── */
export interface StatItem {
  id: string;
  prefix?: string;
  target: number;
  suffix: string;
  decimals?: number;
  label: string;
  static?: false;
}
export interface StatItemStatic {
  id: string;
  value: string;
  label: string;
  static: true;
}
export type AnyStatItem = StatItem | StatItemStatic;

export const HERO_STATS: AnyStatItem[] = [
  {
    id: "stolen",
    prefix: "$",
    target: 12.4,
    suffix: "B",
    decimals: 1,
    label: "Crypto stolen globally in 2024",
  },
  {
    id: "complaints",
    target: 47000,
    suffix: "+",
    label: "NCRP cyber fraud complaints (2024)",
  },
  {
    id: "growth",
    target: 3.2,
    suffix: "×",
    decimals: 1,
    label: "Year-on-year growth in USDT fraud",
  },
  {
    id: "speed",
    value: "< 5 min",
    label: "Wallet → VASP identified by Argus",
    static: true,
  },
];

/** ─── Chart data ─── */
export const CRIME_BY_YEAR = [
  { year: "2018", value: 1.7 },
  { year: "2019", value: 2.8 },
  { year: "2020", value: 4.1 },
  { year: "2021", value: 7.7 },
  { year: "2022", value: 9.2 },
  { year: "2023", value: 11.1 },
  { year: "2024", value: 12.4 },
];

export const TYPOLOGY_DATA = [
  { name: "Investment Scam", value: 38, fill: "#f5a524" },
  { name: "Task-Based Fraud", value: 22, fill: "#22d3ee" },
  { name: "Ransomware", value: 14, fill: "#ff3b5c" },
  { name: "Sextortion", value: 12, fill: "#a78bfa" },
  { name: "Phishing", value: 9, fill: "#34d399" },
  { name: "Darknet", value: 5, fill: "#fb923c" },
];

export const CHAIN_DATA = [
  { chain: "BTC", 2022: 3.1, 2023: 3.8, 2024: 4.1 },
  { chain: "ETH", 2022: 2.4, 2023: 2.9, 2024: 3.2 },
  { chain: "TRON", 2022: 1.1, 2023: 2.2, 2024: 3.4 },
  { chain: "USDT", 2022: 0.8, 2023: 1.4, 2024: 1.7 },
];

export const FROZEN_FUNDS = [
  { month: "Jan", crore: 2.1 },
  { month: "Feb", crore: 3.4 },
  { month: "Mar", crore: 4.8 },
  { month: "Apr", crore: 5.2 },
  { month: "May", crore: 7.1 },
  { month: "Jun", crore: 9.3 },
  { month: "Jul", crore: 10.8 },
  { month: "Aug", crore: 12.4 },
  { month: "Sep", crore: 14.7 },
  { month: "Oct", crore: 16.2 },
  { month: "Nov", crore: 18.9 },
  { month: "Dec", crore: 22.1 },
];

/** ─── Gallery items ─── */
export type GalleryItemType =
  | "graph-crime"
  | "graph-typology"
  | "graph-chain"
  | "graph-frozen"
  | "mock-wallet"
  | "mock-risk"
  | "mock-kanban"
  | "mock-alerts"
  | "mock-victims"
  | "mock-report";

export interface GalleryItem {
  id: string;
  type: GalleryItemType;
  label: string;
}

export const GALLERY_ITEMS: GalleryItem[] = [
  { id: "g1", type: "graph-crime", label: "Crypto Crime 2018–2024" },
  { id: "g2", type: "mock-wallet", label: "Wallet Tracer" },
  { id: "g3", type: "graph-typology", label: "Fraud Typology" },
  { id: "g4", type: "mock-risk", label: "Risk Score Panel" },
  { id: "g5", type: "graph-chain", label: "Chain Distribution" },
  { id: "g6", type: "mock-kanban", label: "Case Management" },
  { id: "g7", type: "graph-frozen", label: "Funds Frozen (₹ Cr)" },
  { id: "g8", type: "mock-alerts", label: "Live Alert Feed" },
  { id: "g9", type: "mock-victims", label: "Cross-Victim View" },
  { id: "g10", type: "mock-report", label: "Freeze Request" },
];
