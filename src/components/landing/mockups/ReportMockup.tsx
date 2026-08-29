import React from "react";

interface ReportMockupProps {
  className?: string;
}

export const ReportMockup: React.FC<ReportMockupProps> = ({
  className = "",
}) => {
  const sections = [
    { title: "Executive Summary", progress: 100, status: "complete" },
    { title: "Timeline Analysis", progress: 100, status: "complete" },
    { title: "Entity Identification", progress: 100, status: "complete" },
    { title: "Fund Flow Diagram", progress: 85, status: "processing" },
    { title: "Risk Assessment", progress: 60, status: "processing" },
    { title: "Legal Recommendations", progress: 0, status: "pending" },
  ];

  const stats = [
    { label: "Addresses Traced", value: "1,247" },
    { label: "Transactions", value: "8,392" },
    { label: "Total Volume", value: "$4.2M" },
    { label: "Confidence", value: "94%" },
  ];

  return (
    <div
      className={`w-full h-full bg-[#050810] border border-[#22d3ee]/20 rounded-lg p-4 overflow-hidden ${className}`}
    >
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-sm font-semibold text-[#f0f4ff] font-['Inter_Tight']">
            Investigation Report
          </h3>
          <p className="text-[10px] text-[#4a5568] font-mono mt-0.5">
            Case #IR-2026-04821
          </p>
        </div>
        <button className="px-3 py-1.5 bg-[#f5a524] hover:bg-[#f5a524]/80 text-[#050810] text-xs font-bold rounded transition-colors font-['Inter_Tight']">
          Export PDF
        </button>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-4 gap-2 mb-4">
        {stats.map((stat, idx) => (
          <div
            key={idx}
            className="bg-[#0a0f1a] border border-[#22d3ee]/10 rounded p-2"
          >
            <div className="text-[9px] text-[#4a5568] font-mono mb-1">
              {stat.label}
            </div>
            <div className="text-sm font-bold text-[#f5a524] font-mono">
              {stat.value}
            </div>
          </div>
        ))}
      </div>

      {/* Report Sections */}
      <div className="space-y-2 mb-4">
        {sections.map((section, idx) => (
          <div
            key={idx}
            className="bg-[#0a0f1a] border border-[#22d3ee]/10 rounded-lg p-3 hover:border-[#f5a524]/40 transition-colors"
          >
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-medium text-[#f0f4ff] font-['Inter_Tight']">
                {section.title}
              </span>
              <span
                className={`text-[9px] font-bold px-2 py-0.5 rounded ${
                  section.status === "complete"
                    ? "bg-[#22d3ee]/20 text-[#22d3ee]"
                    : section.status === "processing"
                      ? "bg-[#f5a524]/20 text-[#f5a524]"
                      : "bg-[#4a5568]/20 text-[#4a5568]"
                }`}
              >
                {section.status.toUpperCase()}
              </span>
            </div>

            <div className="w-full h-1.5 bg-[#050810] rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-500 ${
                  section.status === "complete"
                    ? "bg-[#22d3ee]"
                    : section.status === "processing"
                      ? "bg-[#f5a524]"
                      : "bg-[#4a5568]"
                }`}
                style={{
                  width: `${section.progress}%`,
                  animation:
                    section.status === "processing"
                      ? "pulse 2s ease-in-out infinite"
                      : "none",
                }}
              />
            </div>
          </div>
        ))}
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between pt-3 border-t border-[#22d3ee]/10">
        <div className="text-[10px] text-[#4a5568] font-mono">
          Generated:{" "}
          {new Date().toLocaleDateString("en-US", {
            month: "short",
            day: "numeric",
            year: "numeric",
          })}
        </div>
        <div className="flex items-center space-x-2">
          <div className="w-2 h-2 rounded-full bg-[#f5a524] animate-pulse" />
          <span className="text-[10px] text-[#4a5568] font-mono">
            Auto-updating
          </span>
        </div>
      </div>
    </div>
  );
};
