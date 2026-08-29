import React from "react";

interface CaseKanbanMockupProps {
  className?: string;
}

export const CaseKanbanMockup: React.FC<CaseKanbanMockupProps> = ({
  className = "",
}) => {
  const columns = [
    { title: "Identified", count: 12, color: "#22d3ee" },
    { title: "Investigating", count: 8, color: "#f5a524" },
    { title: "Evidence", count: 5, color: "#ff3b5c" },
    { title: "Closed", count: 23, color: "#4a5568" },
  ];

  const cards = [
    { col: 0, title: "Phishing Campaign #4821", amount: "$142K", risk: "HIGH" },
    { col: 0, title: "Mixer Trail #3309", amount: "$88K", risk: "MED" },
    { col: 1, title: "Exchange Laundering", amount: "$521K", risk: "CRIT" },
    { col: 1, title: "NFT Wash Trading", amount: "$67K", risk: "MED" },
    { col: 2, title: "Ransomware Trace", amount: "$1.2M", risk: "CRIT" },
    { col: 3, title: "Rug Pull Investigation", amount: "$340K", risk: "HIGH" },
  ];

  return (
    <div
      className={`w-full h-full bg-[#050810] border border-[#22d3ee]/20 rounded-lg p-4 overflow-hidden ${className}`}
    >
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-[#f0f4ff] font-['Inter_Tight']">
          Case Pipeline
        </h3>
        <div className="text-xs text-[#4a5568] font-mono">Q1 2026</div>
      </div>

      <div className="grid grid-cols-4 gap-3 h-[calc(100%-3rem)]">
        {columns.map((col, idx) => (
          <div key={idx} className="flex flex-col space-y-2">
            <div className="flex items-center justify-between pb-2 border-b border-[#22d3ee]/10">
              <span className="text-xs font-medium text-[#f0f4ff] font-['Inter_Tight']">
                {col.title}
              </span>
              <span
                className="text-xs font-bold font-mono px-1.5 py-0.5 rounded"
                style={{ backgroundColor: `${col.color}20`, color: col.color }}
              >
                {col.count}
              </span>
            </div>

            <div className="space-y-2 overflow-hidden">
              {cards
                .filter((c) => c.col === idx)
                .map((card, i) => (
                  <div
                    key={i}
                    className="bg-[#0a0f1a] border border-[#22d3ee]/10 rounded p-2.5 hover:border-[#f5a524]/40 transition-colors"
                  >
                    <div className="flex items-start justify-between mb-1.5">
                      <span className="text-xs font-medium text-[#f0f4ff] leading-tight font-['Inter_Tight']">
                        {card.title}
                      </span>
                      <span
                        className={`text-[9px] font-bold px-1 py-0.5 rounded ${
                          card.risk === "CRIT"
                            ? "bg-[#ff3b5c]/20 text-[#ff3b5c]"
                            : card.risk === "HIGH"
                              ? "bg-[#f5a524]/20 text-[#f5a524]"
                              : "bg-[#22d3ee]/20 text-[#22d3ee]"
                        }`}
                      >
                        {card.risk}
                      </span>
                    </div>
                    <div className="text-xs font-bold text-[#f5a524] font-mono">
                      {card.amount}
                    </div>
                    <div className="flex items-center mt-2 pt-2 border-t border-[#22d3ee]/5">
                      <div className="w-5 h-5 rounded-full bg-gradient-to-br from-[#22d3ee] to-[#f5a524] mr-2" />
                      <span className="text-[10px] text-[#4a5568] font-mono">
                        Analyst 0x{Math.random().toString(16).slice(2, 6)}
                      </span>
                    </div>
                  </div>
                ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
