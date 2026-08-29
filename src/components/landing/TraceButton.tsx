import React from "react";

interface TraceButtonProps {
  scale: number;
  onClick?: () => void;
}

export const TraceButton: React.FC<TraceButtonProps> = ({ scale, onClick }) => {
  return (
    <div
      className="fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 z-30 pointer-events-auto"
      style={{
        transform: `translate(-50%, -50%) scale(${scale})`,
        opacity: scale,
      }}
    >
      <button
        onClick={onClick}
        className="px-8 py-4 bg-[#f5a524] hover:bg-[#f5a524]/80 text-[#050810] text-lg font-bold rounded-full transition-all duration-300 shadow-[0_0_40px_rgba(245,165,36,0.5)] hover:shadow-[0_0_60px_rgba(245,165,36,0.7)] font-['Inter_Tight']"
      >
        Start Tracing →
      </button>
    </div>
  );
};
