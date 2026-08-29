import { Canvas } from "@react-three/fiber";
import { Suspense, useEffect } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

import { attachPointer } from "@/lib/pointer";
import { setCoinProgress, useCoinProgress } from "@/lib/coin-scroll-store";
import { band } from "@/lib/scroll-store";
import { CoinScene } from "./CoinScene";

gsap.registerPlugin(ScrollTrigger);

type Beat = {
  id: string;
  index: string;
  kicker: string;
  title: string;
  body: string;
  win: [number, number, number, number];
  align: "left" | "right" | "center";
};

const BEATS: Beat[] = [
  {
    id: "btc-rise",
    index: "01",
    kicker: "Bitcoin on-chain",
    title: "The coin emerges from the chain.",
    body: "Every Bitcoin transaction is permanent, traceable, and court-ready. Argus surfaces the wallet behind every satoshi.",
    win: [0.04, 0.12, 0.28, 0.36],
    align: "left",
  },
  {
    id: "btc-trace",
    index: "02",
    kicker: "Multi-hop tracing",
    title: "We follow the money, hop by hop.",
    body: "Funds rarely stay in one wallet. Argus traces through layering wallets, mixers and bridges until we identify the cash-out exchange.",
    win: [0.36, 0.44, 0.58, 0.66],
    align: "right",
  },
  {
    id: "btc-freeze",
    index: "03",
    kicker: "VASP identification",
    title: "Find the cash-out point. Freeze it.",
    body: "Every laundering trail ends at an exchange. We surface the exact chokepoint where assets can be frozen before the criminal cashes out.",
    win: [0.66, 0.73, 0.84, 0.92],
    align: "left",
  },
];

function CoinOverlay() {
  const p = useCoinProgress();

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
              pointerEvents: "none",
            }}
          >
            <p className="beat__kicker">
              <span className="beat__index">{b.index}</span>
              {b.kicker}
            </p>
            <h2 className="beat__title">{b.title}</h2>
            <p className="beat__body">{b.body}</p>
          </div>
        );
      })}

      <div className="progress-rail">
        <span
          className="progress-rail__fill"
          style={{ transform: `scaleY(${p})` }}
        />
      </div>
    </div>
  );
}

function CoinScrollController() {
  useEffect(() => {
    const st = ScrollTrigger.create({
      trigger: "#coin-story",
      start: "top top",
      end: "bottom bottom",
      pin: "#coin-stage",
      pinSpacing: false,
      scrub: 0.25,
      onUpdate: (self) => setCoinProgress(self.progress),
      onRefresh: (self) => setCoinProgress(self.progress),
    });
    return () => st.kill();
  }, []);
  return null;
}

export function CoinSection() {
  useEffect(() => attachPointer(), []);

  return (
    <section id="coin-story" className="relative w-full bg-background">
      <CoinScrollController />
      <div id="coin-stage" className="relative h-screen w-full overflow-hidden">
        <Canvas
          className="!absolute inset-0"
          dpr={[1, 1.5]}
          gl={{ antialias: true, powerPreference: "high-performance" }}
          camera={{ position: [0, 0, 22], fov: 50, near: 0.1, far: 200 }}
        >
          <Suspense fallback={null}>
            <CoinScene />
          </Suspense>
        </Canvas>
        <div className="stage-vignette" />
        <CoinOverlay />
      </div>
      {/* 600vh -- enough for 3 beats to play out cleanly */}
      <div className="h-[600vh]" aria-hidden="true" />
    </section>
  );
}
