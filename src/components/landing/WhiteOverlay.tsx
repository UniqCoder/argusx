import React from "react";

interface WhiteOverlayProps {
  opacity: number;
}

export const WhiteOverlay: React.FC<WhiteOverlayProps> = ({ opacity }) => {
  return (
    <div
      className="fixed inset-0 bg-[#0a0f1a]/95 backdrop-blur-sm z-20 pointer-events-none flex items-end justify-center pb-16"
      style={{ opacity }}
    >
      <div className="max-w-4xl px-8 text-center space-y-6" style={{ opacity }}>
        <h2 className="text-4xl font-bold text-[#f0f4ff] font-['Inter_Tight']">
          Ready to trace blockchain fraud?
        </h2>

        <p className="text-lg text-[#f0f4ff]/70 font-['Inter_Tight'] leading-relaxed">
          Join law enforcement agencies, financial institutions, and
          cybersecurity teams using Argus to investigate crypto crime and
          recover stolen funds.
        </p>

        <div className="flex items-center justify-center space-x-6 pt-4">
          <div className="text-center">
            <div className="text-3xl font-bold text-[#f5a524] font-mono">
              10M+
            </div>
            <div className="text-sm text-[#4a5568] font-['Inter_Tight'] mt-1">
              Addresses Mapped
            </div>
          </div>

          <div className="w-px h-12 bg-[#22d3ee]/20" />

          <div className="text-center">
            <div className="text-3xl font-bold text-[#22d3ee] font-mono">
              $2.4B
            </div>
            <div className="text-sm text-[#4a5568] font-['Inter_Tight'] mt-1">
              Funds Traced
            </div>
          </div>

          <div className="w-px h-12 bg-[#22d3ee]/20" />

          <div className="text-center">
            <div className="text-3xl font-bold text-[#f5a524] font-mono">
              120+
            </div>
            <div className="text-sm text-[#4a5568] font-['Inter_Tight'] mt-1">
              Organizations
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="pt-12 border-t border-[#22d3ee]/10 mt-12">
          <div className="flex items-center justify-between text-xs text-[#4a5568] font-mono">
            <div>© 2026 Argus. All rights reserved.</div>
            <div className="flex items-center space-x-6">
              <button className="hover:text-[#f5a524] transition-colors">
                Privacy
              </button>
              <button className="hover:text-[#f5a524] transition-colors">
                Terms
              </button>
              <button className="hover:text-[#f5a524] transition-colors">
                Contact
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
