import React, { useRef, useEffect, useState } from "react";
import { GalleryCard } from "./GalleryCard";
import { CrimeByYearChart } from "./charts/CrimeByYearChart";
import { TypologyPieChart } from "./charts/TypologyPieChart";
import { ChainBarChart } from "./charts/ChainBarChart";
import { FrozenFundsChart } from "./charts/FrozenFundsChart";
import { WalletTracerMockup } from "./mockups/WalletTracerMockup";
import { RiskScoreMockup } from "./mockups/RiskScoreMockup";
import { CaseKanbanMockup } from "./mockups/CaseKanbanMockup";
import { AlertFeedMockup } from "./mockups/AlertFeedMockup";
import { CrossVictimMockup } from "./mockups/CrossVictimMockup";
import { ReportMockup } from "./mockups/ReportMockup";

interface GalleryGridProps {
  innerTranslateY: number; // from LandingPage RAF
}

// Layout algorithm from prmpt template - deterministic scatter
const buildLayout = (count: number, cols: number = 3) => {
  const positions: { x: number; y: number }[] = [];
  const colWidth = 100 / cols;
  const rowHeight = 40; // viewport-relative spacing

  for (let i = 0; i < count; i++) {
    const col = i % cols;
    const row = Math.floor(i / cols);

    // Base grid position
    const baseX = colWidth * col + colWidth / 2;
    const baseY = row * rowHeight + 20;

    // Scatter offset for organic feel
    const scatterX = ((i * 37) % 20) - 10; // -10 to +10
    const scatterY = ((i * 53) % 15) - 7.5; // -7.5 to +7.5

    positions.push({
      x: baseX + scatterX,
      y: baseY + scatterY,
    });
  }

  return positions;
};

const galleryItems = [
  { id: "crime-year", component: CrimeByYearChart },
  { id: "typology", component: TypologyPieChart },
  { id: "chain", component: ChainBarChart },
  { id: "frozen", component: FrozenFundsChart },
  { id: "wallet-tracer", component: WalletTracerMockup },
  { id: "risk-score", component: RiskScoreMockup },
  { id: "kanban", component: CaseKanbanMockup },
  { id: "alerts", component: AlertFeedMockup },
  { id: "cross-victim", component: CrossVictimMockup },
  { id: "report", component: ReportMockup },
];

const positions = buildLayout(galleryItems.length, 3);

export const GalleryGrid: React.FC<GalleryGridProps> = ({
  innerTranslateY,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [scales, setScales] = useState<number[]>(galleryItems.map(() => 0));
  const rafRef = useRef<number>();

  useEffect(() => {
    const updateScales = () => {
      if (!containerRef.current) return;

      const vh = window.innerHeight;
      const viewportCenter = vh / 2;

      const newScales = galleryItems.map((_, idx) => {
        const card = containerRef.current?.querySelector(
          `[data-card-index="${idx}"]`,
        );
        if (!card) return 0;

        const rect = card.getBoundingClientRect();
        const cardCenter = rect.top + rect.height / 2;
        const distanceFromCenter = Math.abs(cardCenter - viewportCenter);

        // Scale based on distance from viewport center
        const maxDistance = vh * 0.6;
        const scale = Math.max(0, 1 - distanceFromCenter / maxDistance);

        return scale;
      });

      setScales(newScales);
      rafRef.current = requestAnimationFrame(updateScales);
    };

    rafRef.current = requestAnimationFrame(updateScales);

    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [innerTranslateY]);

  return (
    <div
      ref={containerRef}
      className="relative w-full"
      style={{
        height: "400vh", // Space for cards to scroll through
        transform: `translateY(${innerTranslateY}px)`,
      }}
    >
      {galleryItems.map((item, idx) => {
        const Component = item.component;
        return (
          <div key={item.id} data-card-index={idx}>
            <GalleryCard
              x={positions[idx].x}
              y={positions[idx].y}
              index={idx}
              scale={scales[idx]}
            >
              <Component />
            </GalleryCard>
          </div>
        );
      })}
    </div>
  );
};
