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
  /**
   * The engine's own correlation_score [0,1] (see
   * correlation_service.calculate_correlation_score). The signal bars used to
   * be hardcoded to 88% / 55% / 25% regardless of what the API actually
   * returned — this is the real number those bars now read from.
   */
  correlationScore: number;
}

export function formatInr(n: number): string {
  if (n >= 1e7) return `₹${(n / 1e7).toFixed(1)}Cr`;
  if (n >= 1e5) return `₹${(n / 1e5).toFixed(1)}L`;
  return `₹${n.toLocaleString("en-IN")}`;
}

/**
 * `nonce` lets a caller force a fresh request for the SAME [address, chain] —
 * pressing "Correlate" a second time on an unchanged address used to do
 * nothing, because React bails on an identical effect dependency and the
 * button had no other way to signal "ask again". Bump the nonce on every
 * press; `address`/`chain` alone still work for the normal case of searching
 * a new wallet.
 */
export function useCorrelation(
  address: string | null,
  chain: Chain,
  nonce = 0,
) {
  const [signal, setSignal] = useState<NetworkSignal | null>(null);
  const [linkedComplaints, setLinkedComplaints] = useState<Complaint[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    if (!address) return;
    let cancelled = false;

    // Clear the PREVIOUS wallet's result before starting the new one.
    // Without this, `loading` flipped true but `signal` kept showing the
    // last wallet's victim count and funds-at-risk for the whole request —
    // a stale answer presented as the current one.
    setSignal(null);
    setLinkedComplaints([]);
    setNotFound(false);
    setLoading(true);
    setError(null);

    correlate({ address, chain })
      .then((data) => {
        if (cancelled) return;
        const count = data.linked_complaints.length;
        // Bucketed from the backend's own correlation_score (which already
        // factors in distinct geographies via calculate_correlation_score),
        // not recomputed from raw complaint count. Re-bucketing on count
        // alone used to disagree with the score this same response carried —
        // e.g. two complaints across two states scores ~0.60 on the backend
        // but a same-state pair scores ~0.50, yet both showed as "MEDIUM"
        // here regardless. The bands mirror the score's own generation
        // curve (correlation_service.calculate_correlation_score): 0.70+ is
        // the 3-4-complaint band, 0.30+ is the 2-complaint band.
        const strength: "HIGH" | "MEDIUM" | "LOW" =
          data.correlation_score >= 0.7
            ? "HIGH"
            : data.correlation_score >= 0.3
              ? "MEDIUM"
              : "LOW";
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
          correlationScore: data.correlation_score,
        });
        setLinkedComplaints(data.linked_complaints);
      })
      .catch((e) => {
        if (cancelled) return;
        // A wallet the system has never seen is an honest, common outcome —
        // not an error. Distinguished so the page can say "no complaints
        // reference this wallet" instead of a red failure banner.
        if (e?.status === 404 || e?.code === "WALLET_NOT_FOUND") {
          setNotFound(true);
        } else {
          setError(e instanceof Error ? e.message : "Correlation failed");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [address, chain, nonce]);

  return { signal, linkedComplaints, loading, error, notFound };
}
