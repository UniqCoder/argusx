import { band, useScrollProgress } from "@/lib/scroll-store";
import { MagneticButton } from "./MagneticButton";
import { useAuthStore } from "@/store/auth-store";

type Beat = {
  id: string;
  index: string;
  kicker: string;
  title: string;
  body: string;
  win: [number, number, number, number];
  align: "left" | "right" | "center";
  cta?: boolean;
};

const BEATS: Beat[] = [
  {
    id: "discovery",
    index: "01",
    kicker: "Cyber fraud intelligence",
    title: "Every suspect wallet leaves a trail.",
    body: "Argus is built for India's cyber cells - I4C, NCRP, state units. Paste a wallet address and we trace it across Bitcoin, Ethereum and TRON in minutes, not days.",
    win: [-0.05, -0.02, 0.08, 0.16],
    align: "left",
    cta: true,
  },
  {
    id: "emergence",
    index: "02",
    kicker: "Multi-hop tracing",
    title: "We follow the money, hop by hop.",
    body: "Funds rarely stay in one wallet. Argus traces through layering wallets, mixers and bridges - every hop logged - until we identify the cash-out exchange.",
    win: [0.16, 0.22, 0.3, 0.36],
    align: "right",
  },
  {
    id: "immersion",
    index: "03",
    kicker: "VASP identification",
    title: "Find the cash-out point.",
    body: "Every laundering trail ends at an exchange. We surface the nearest VASP - the exact chokepoint where assets can be frozen before the criminal cashes out.",
    win: [0.37, 0.42, 0.46, 0.5],
    align: "left",
  },
  {
    id: "through",
    index: "04",
    kicker: "On-chain evidence",
    title: "Every line of data is a defensible fact.",
    body: "Transactions, timestamps, hop distances - stored as a concrete evidence chain, ready for a freeze request, SAHYOG escalation, or court submission.",
    win: [0.52, 0.56, 0.6, 0.64],
    align: "center",
  },
  {
    id: "universe",
    index: "05",
    kicker: "Scale of the problem",
    title: "Millions of wallets. One platform.",
    body: "Investment scams, task-based fraud, sextortion, ransomware - all move value on-chain. Argus monitors the full landscape from a single investigator dashboard.",
    win: [0.65, 0.69, 0.73, 0.77],
    align: "right",
  },
  {
    id: "multichain",
    index: "06",
    kicker: "Multi-chain support",
    title: "BTC. ETH. TRON. All in one view.",
    body: "Fraudsters chain-hop to break audit trails. Argus clusters wallets across Bitcoin, Ethereum, TRON and USDT-TRC20 and keeps the investigation intact.",
    win: [0.76, 0.79, 0.83, 0.86],
    align: "left",
  },
  {
    id: "tron",
    index: "07",
    kicker: "Transaction tracing",
    title: "Follow every hop. Catch the launderer.",
    body: "Watch a single USDT flow travel wallet to wallet in real time. Argus maps the full path - layering patterns, peel chains, mixer proximity - all flagged automatically.",
    win: [0.85, 0.88, 0.91, 0.93],
    align: "right",
  },
  {
    id: "investigation",
    index: "08",
    kicker: "Risk signal detected",
    title: "Suspicious cluster identified.",
    body: "Risk tier, SHAP evidence, linked complaints, nearest VASP - one panel. One click generates a standardised freeze request ready to send to the exchange compliance desk.",
    win: [0.93, 0.955, 1.01, 1.02],
    align: "left",
    cta: true,
  },
];

export function StoryOverlay() {
  const p = useScrollProgress();
  const openAuth = useAuthStore((s) => s.open);

  return (
    <div className="pointer-events-none absolute inset-0 z-10">
      {BEATS.map((b) => {
        const o = band(p, b.win[0], b.win[1], b.win[2], b.win[3]);
        const drift =
          (1 - o) * (b.align === "right" ? 42 : b.align === "left" ? -42 : 0);
        const lift = (1 - o) * 26;
        const hidden = o < 0.005;

        return (
          <div
            key={b.id}
            className={`beat beat--${b.align}`}
            style={{
              opacity: o,
              transform: `translate3d(${drift}px, ${lift}px, 0)`,
              visibility: hidden ? "hidden" : "visible",
              pointerEvents: hidden ? "none" : undefined,
            }}
          >
            <p className="beat__kicker">
              <span className="beat__index">{b.index}</span>
              {b.kicker}
            </p>
            <h2 className="beat__title">{b.title}</h2>
            <p className="beat__body">{b.body}</p>
            {b.cta && (
              <div
                className="pointer-events-auto mt-8 flex flex-wrap gap-3"
                style={{ pointerEvents: hidden ? "none" : "auto" }}
              >
                <MagneticButton onClick={() => openAuth("signup")}>
                  Trace a wallet
                </MagneticButton>
              </div>
            )}
          </div>
        );
      })}

      <div className="progress-rail">
        <span
          className="progress-rail__fill"
          style={{ transform: `scaleY(${p})` }}
        />
      </div>

      <div className="scroll-hint" style={{ opacity: 1 - Math.min(1, p * 16) }}>
        <span>Scroll to see how it works</span>
        <span className="scroll-hint__line" />
      </div>
    </div>
  );
}
