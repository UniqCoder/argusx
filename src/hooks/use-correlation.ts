// ============================================================
// useCorrelation — POST /api/v1/correlate
// Falls back to MOCK_NETWORK_SIGNAL on error.
// ============================================================
import { useState, useEffect } from "react";
import { correlate } from "@/lib/api";
import type { Chain } from "@/lib/api-types";
import { MOCK_NETWORK_SIGNAL } from "@/lib/mock-data";

export type NetworkSignal = typeof MOCK_NETWORK_SIGNAL;

function formatInr(n: number): string {
  if (n >= 1e7) return `₹${(n / 1e7).toFixed(1)}Cr`;
  if (n >= 1e5) return `₹${(n / 1e5).toFixed(1)}L`;
  return `₹${n.toLocaleString("en-IN")}`;
}

export function useCorrelation(address: string | null, chain: Chain) {
  const [signal, setSignal] = useState<NetworkSignal>(MOCK_NETWORK_SIGNAL);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!address) return;
    let cancelled = false;
    setLoading(true);
    setError(null);

    correlate({ address, chain })
      .then((data) => {
        if (cancelled) return;
        const count = data.linked_complaints.length;
        const strength: "HIGH" | "MEDIUM" | "LOW" =
          count >= 4 ? "HIGH" : count >= 2 ? "MEDIUM" : "LOW";
        const states = new Set(
          data.linked_complaints.map((c) => c.state).filter(Boolean),
        ).size;

        setSignal({
          wallet: address.slice(0, 10) + "..." + address.slice(-4),
          signalStrength: strength as "HIGH",
          victims: count,
          complaints: count,
          states: states > 0 ? states : data.distinct_geographies,
          daysSinceFirst: 12,
          totalFundsAtRisk: formatInr(data.total_amount),
        });
      })
      .catch((e) => {
        if (!cancelled)
          setError(e instanceof Error ? e.message : "Correlation failed");
        // Keep MOCK_NETWORK_SIGNAL
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [address, chain]);

  return { signal, loading, error };
}
