import React from "react";

export const HeroOverlay: React.FC = () => {
  return (
    <>
      {/* Logo */}
      <div className="fixed top-8 left-8 z-20 pointer-events-none">
        <h1
          className="text-2xl font-bold font-['Inter_Tight']"
          style={{ mixBlendMode: "exclusion", color: "#f0f4ff" }}
        >
          Argus
        </h1>
      </div>

      {/* Navigation */}
      <nav className="fixed top-8 right-8 z-20 pointer-events-auto">
        <div
          className="flex items-center space-x-6 text-sm font-medium font-['Inter_Tight']"
          style={{ mixBlendMode: "exclusion", color: "#f0f4ff" }}
        >
          <button className="hover:text-[#f5a524] transition-colors">
            Platform
          </button>
          <button className="hover:text-[#f5a524] transition-colors">
            Solutions
          </button>
          <button className="hover:text-[#f5a524] transition-colors">
            Docs
          </button>
          <button className="px-4 py-2 border border-current rounded hover:bg-[#f0f4ff]/10 transition-colors">
            Sign In
          </button>
        </div>
      </nav>

      {/* Caption */}
      <div className="fixed bottom-24 left-8 z-20 pointer-events-none max-w-md">
        <p
          className="text-xs leading-relaxed font-['Inter_Tight'] opacity-70"
          style={{ mixBlendMode: "exclusion", color: "#f0f4ff" }}
        >
          Blockchain forensics platform powered by AI. Trace crypto fraud across
          chains, identify perpetrators, and build court-ready evidence in
          minutes.
        </p>
      </div>

      {/* Product info */}
      <div className="fixed bottom-8 left-8 z-20 pointer-events-none">
        <div
          className="flex items-center space-x-4 text-[10px] font-mono uppercase tracking-wider"
          style={{ mixBlendMode: "exclusion", color: "#f0f4ff" }}
        >
          <span>Blockchain Intelligence</span>
          <span className="opacity-30">•</span>
          <span>AI-Powered</span>
          <span className="opacity-30">•</span>
          <span>Real-Time Tracing</span>
        </div>
      </div>

      {/* Scroll indicator */}
      <div className="fixed bottom-8 right-8 z-20 pointer-events-none">
        <div
          className="flex flex-col items-center space-y-2"
          style={{ mixBlendMode: "exclusion", color: "#f0f4ff" }}
        >
          <span className="text-[10px] font-mono uppercase tracking-wider">
            Scroll
          </span>
          <div className="w-px h-12 bg-current opacity-30" />
        </div>
      </div>
    </>
  );
};
