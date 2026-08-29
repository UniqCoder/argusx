import React from "react";

interface AlertFeedMockupProps {
  className?: string;
}

export const AlertFeedMockup: React.FC<AlertFeedMockupProps> = ({
  className = "",
}) => {
  const alerts = [
    {
      time: "2m ago",
      type: "CRITICAL",
      text: "High-risk wallet detected in transaction chain",
      addr: "0x742d...8f2a",
    },
    {
      time: "8m ago",
      type: "WARNING",
      text: "Unusual transaction pattern: 15 hops in 3 minutes",
      addr: "0x9c1e...4b3d",
    },
    {
      time: "14m ago",
      type: "INFO",
      text: "New entity cluster identified with 47 addresses",
      addr: "0x5a8f...7e1c",
    },
    {
      time: "21m ago",
      type: "CRITICAL",
      text: "Known mixer service interaction detected",
      addr: "0xe3b9...2d4a",
    },
    {
      time: "35m ago",
      type: "WARNING",
      text: "Potential sybil attack: 120+ linked identities",
      addr: "0x1f7c...9a8e",
    },
  ];

  const getAlertColor = (type: string) => {
    switch (type) {
      case "CRITICAL":
        return { bg: "#ff3b5c", text: "#ff3b5c" };
      case "WARNING":
        return { bg: "#f5a524", text: "#f5a524" };
      default:
        return { bg: "#22d3ee", text: "#22d3ee" };
    }
  };

  return (
    <div
      className={`w-full h-full bg-[#050810] border border-[#22d3ee]/20 rounded-lg p-4 overflow-hidden ${className}`}
    >
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-[#f0f4ff] font-['Inter_Tight']">
          Live Alert Feed
        </h3>
        <div className="flex items-center space-x-2">
          <div className="w-2 h-2 rounded-full bg-[#22d3ee] animate-pulse" />
          <span className="text-xs text-[#4a5568] font-mono">LIVE</span>
        </div>
      </div>

      <div className="space-y-2 overflow-y-auto h-[calc(100%-3rem)]">
        {alerts.map((alert, idx) => {
          const colors = getAlertColor(alert.type);
          return (
            <div
              key={idx}
              className="bg-[#0a0f1a] border border-[#22d3ee]/10 rounded-lg p-3 hover:border-[#f5a524]/40 transition-all duration-200"
              style={{
                animation: `slideInLeft 0.3s ease-out ${idx * 0.1}s both`,
              }}
            >
              <div className="flex items-start justify-between mb-2">
                <span
                  className="text-[10px] font-bold px-2 py-1 rounded"
                  style={{
                    backgroundColor: `${colors.bg}20`,
                    color: colors.text,
                  }}
                >
                  {alert.type}
                </span>
                <span className="text-[10px] text-[#4a5568] font-mono">
                  {alert.time}
                </span>
              </div>

              <p className="text-xs text-[#f0f4ff] mb-2 leading-relaxed font-['Inter_Tight']">
                {alert.text}
              </p>

              <div className="flex items-center justify-between pt-2 border-t border-[#22d3ee]/5">
                <code className="text-[10px] text-[#22d3ee] font-mono">
                  {alert.addr}
                </code>
                <button className="text-[10px] text-[#f5a524] hover:text-[#22d3ee] transition-colors font-medium">
                  Investigate →
                </button>
              </div>
            </div>
          );
        })}
      </div>

      <style>{`
        @keyframes slideInLeft {
          from {
            opacity: 0;
            transform: translateX(-20px);
          }
          to {
            opacity: 1;
            transform: translateX(0);
          }
        }
      `}</style>
    </div>
  );
};
