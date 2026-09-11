// ============================================================
// useCorrelation — POST /api/v1/correlate
// Real data only — no silent mock fallback. `signal` is null until a real
// result arrives; callers show their own loading/empty/error state.
// ============================================================
import { useState, useEffect } from "react";
import { correlate } from "@/lib/api";
import type { Chain, Complaint } from "@/lib/api-types";

export interface NetworkSignal {
  wallet: string;
  signalStrength: "HIGH" | "MEDIUM" | "LOW";
  victims: number;
  complaints: number;
  states: number;
  totalFundsAtRisk: string;
}

function formatInr(n: number): string {
  if (n >= 1e7) return `₹${(n / 1e7).toFixed(1)}Cr`;
  if (n >= 1e5) return `₹${(n / 1e5).toFixed(1)}L`;
  return `₹${n.toLocaleString("en-IN")}`;
}

export function useCorrelation(address: string | null, chain: Chain) {
  const [signal, setSignal] = useState<NetworkSignal | null>(null);
  const [linkedComplaints, setLinkedComplaints] = useState<Complaint[]>([]);
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
          signalStrength: strength,
          victims: count,
          complaints: count,
          states: states > 0 ? states : data.distinct_geographies,
          totalFundsAtRisk: formatInr(data.total_amount),
        });
        setLinkedComplaints(data.linked_complaints);
      })
      .catch((e) => {
        if (!cancelled)
          setError(e instanceof Error ? e.message : "Correlation failed");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [address, chain]);

  return { signal, linkedComplaints, loading, error };
}
