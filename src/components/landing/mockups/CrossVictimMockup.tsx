import React from "react";

interface CrossVictimMockupProps {
  className?: string;
}

export const CrossVictimMockup: React.FC<CrossVictimMockupProps> = ({
  className = "",
}) => {
  const nodes = [
    {
      id: "A",
      x: 20,
      y: 30,
      label: "Victim A",
      amount: "$42K",
      connections: ["B", "C"],
    },
    {
      id: "B",
      x: 50,
      y: 10,
      label: "Scammer",
      amount: "$890K",
      connections: ["A", "C", "D", "E"],
      highlight: true,
    },
    {
      id: "C",
      x: 80,
      y: 30,
      label: "Victim C",
      amount: "$156K",
      connections: ["B", "D"],
    },
    {
      id: "D",
      x: 50,
      y: 60,
      label: "Victim D",
      amount: "$73K",
      connections: ["B", "C", "E"],
    },
    {
      id: "E",
      x: 20,
      y: 80,
      label: "Victim E",
      amount: "$91K",
      connections: ["B", "D"],
    },
  ];

  return (
    <div
      className={`w-full h-full bg-[#050810] border border-[#22d3ee]/20 rounded-lg p-4 overflow-hidden ${className}`}
    >
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-[#f0f4ff] font-['Inter_Tight']">
          Cross-Victim Analysis
        </h3>
        <div className="text-xs text-[#4a5568] font-mono">5 Linked Cases</div>
      </div>

      <div className="relative w-full h-[calc(100%-3rem)] bg-[#0a0f1a] rounded-lg border border-[#22d3ee]/10">
        <svg className="absolute inset-0 w-full h-full">
          {/* Connection lines */}
          {nodes.map((node) =>
            node.connections.map((targetId) => {
              const target = nodes.find((n) => n.id === targetId);
              if (!target) return null;
              return (
                <line
                  key={`${node.id}-${targetId}`}
                  x1={`${node.x}%`}
                  y1={`${node.y}%`}
                  x2={`${target.x}%`}
                  y2={`${target.y}%`}
                  stroke={
                    node.highlight || target.highlight ? "#ff3b5c" : "#22d3ee"
                  }
                  strokeWidth="1"
                  strokeOpacity="0.3"
                  strokeDasharray={
                    node.highlight || target.highlight ? "4 2" : "none"
                  }
                />
              );
            }),
          )}
        </svg>

        {/* Nodes */}
        {nodes.map((node, idx) => (
          <div
            key={node.id}
            className="absolute transform -translate-x-1/2 -translate-y-1/2"
            style={{
              left: `${node.x}%`,
              top: `${node.y}%`,
              animation: `nodeAppear 0.5s ease-out ${idx * 0.1}s both`,
            }}
          >
            <div
              className={`relative flex flex-col items-center ${node.highlight ? "z-10" : ""}`}
            >
              <div
                className={`w-12 h-12 rounded-full border-2 flex items-center justify-center ${
                  node.highlight
                    ? "bg-[#ff3b5c]/20 border-[#ff3b5c] shadow-[0_0_20px_rgba(255,59,92,0.5)]"
                    : "bg-[#22d3ee]/10 border-[#22d3ee]/50"
                }`}
              >
                <span
                  className={`text-xs font-bold font-mono ${
                    node.highlight ? "text-[#ff3b5c]" : "text-[#22d3ee]"
                  }`}
                >
                  {node.id}
                </span>
              </div>

              <div className="mt-2 bg-[#050810]/95 border border-[#22d3ee]/20 rounded px-2 py-1 whitespace-nowrap">
                <div
                  className={`text-[10px] font-medium ${
                    node.highlight ? "text-[#ff3b5c]" : "text-[#f0f4ff]"
                  } font-['Inter_Tight']`}
                >
                  {node.label}
                </div>
                <div className="text-[9px] text-[#f5a524] font-mono font-bold">
                  {node.amount}
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="mt-3 flex items-center justify-between text-[10px]">
        <div className="flex items-center space-x-3">
          <div className="flex items-center">
            <div className="w-3 h-3 rounded-full bg-[#ff3b5c]/20 border border-[#ff3b5c] mr-1" />
            <span className="text-[#4a5568] font-mono">Suspect</span>
          </div>
          <div className="flex items-center">
            <div className="w-3 h-3 rounded-full bg-[#22d3ee]/10 border border-[#22d3ee]/50 mr-1" />
            <span className="text-[#4a5568] font-mono">Victim</span>
          </div>
        </div>
        <span className="text-[#f5a524] font-mono font-bold">
          Total: $1.25M
        </span>
      </div>

      <style>{`
        @keyframes nodeAppear {
          from {
            opacity: 0;
            transform: translate(-50%, -50%) scale(0);
          }
          to {
            opacity: 1;
            transform: translate(-50%, -50%) scale(1);
          }
        }
      `}</style>
    </div>
  );
};
