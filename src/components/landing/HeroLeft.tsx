import React, { useEffect, useRef, useState } from "react";

interface HeroLeftProps {
  opacity: number;
}

const easeOutExpo = (t: number): number => {
  return t === 1 ? 1 : 1 - Math.pow(2, -10 * t);
};

const useCounter = (
  end: number,
  duration: number = 2000,
  delay: number = 0,
) => {
  const [count, setCount] = useState(0);
  const startTimeRef = useRef<number | null>(null);
  const rafRef = useRef<number>();

  useEffect(() => {
    const delayTimeout = setTimeout(() => {
      const animate = (timestamp: number) => {
        if (!startTimeRef.current) startTimeRef.current = timestamp;
        const elapsed = timestamp - startTimeRef.current;
        const progress = Math.min(elapsed / duration, 1);
        const easedProgress = easeOutExpo(progress);

        setCount(Math.floor(easedProgress * end));

        if (progress < 1) {
          rafRef.current = requestAnimationFrame(animate);
        }
      };

      rafRef.current = requestAnimationFrame(animate);
    }, delay);

    return () => {
      clearTimeout(delayTimeout);
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [end, duration, delay]);

  return count;
};

export const HeroLeft: React.FC<HeroLeftProps> = ({ opacity }) => {
  const fraudCount = useCounter(847, 2000, 300);
  const lossCount = useCounter(2400, 2000, 500);
  const tracedCount = useCounter(94, 2000, 700);

  return (
    <div
      className="absolute inset-0 flex items-center justify-center pointer-events-none"
      style={{ opacity }}
    >
      <div className="max-w-xl px-8">
        <div className="space-y-8">
          {/* Main stat */}
          <div className="space-y-3">
            <div className="text-[#4a5568] text-sm font-medium tracking-wider uppercase font-['Inter_Tight']">
              Global Crypto Fraud 2025
            </div>
            <div className="text-[#f0f4ff] text-7xl font-bold font-['Inter_Tight'] leading-none">
              ${lossCount.toLocaleString()}M
            </div>
            <div className="text-[#22d3ee] text-lg font-medium font-['Inter_Tight']">
              stolen in blockchain fraud
            </div>
          </div>

          {/* Secondary stats */}
          <div className="grid grid-cols-2 gap-6 pt-6 border-t border-[#22d3ee]/20">
            <div className="space-y-2">
              <div className="text-[#f5a524] text-4xl font-bold font-['Inter_Tight']">
                {fraudCount.toLocaleString()}
              </div>
              <div className="text-[#4a5568] text-sm font-medium font-['Inter_Tight']">
                Active fraud schemes
              </div>
            </div>

            <div className="space-y-2">
              <div className="text-[#22d3ee] text-4xl font-bold font-['Inter_Tight']">
                {tracedCount}%
              </div>
              <div className="text-[#4a5568] text-sm font-medium font-['Inter_Tight']">
                Successfully traced
              </div>
            </div>
          </div>

          {/* Footer text */}
          <div className="pt-6 border-t border-[#22d3ee]/20">
            <p className="text-[#f0f4ff]/70 text-sm leading-relaxed font-['Inter_Tight']">
              Traditional investigation methods can't keep pace with blockchain
              fraud.
              <span className="text-[#f5a524] font-semibold"> Argus</span>{" "}
              traces funds across chains, identifies perpetrators, and delivers
              court-ready evidence.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};
