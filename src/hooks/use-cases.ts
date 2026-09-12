// ============================================================
// useCases — fetches GET /api/v1/cases
// Real data only — a genuine empty result stays empty; no mock
// fallback on error or on zero cases.
// ============================================================
import { useState, useEffect } from "react";
import { listCases } from "@/lib/api";
import type { Case, CaseStatus as ApiStatus } from "@/lib/api-types";
import type { InvestigationCase, CaseStatus } from "@/lib/mock-data";

const STATUS_MAP: Record<ApiStatus, CaseStatus> = {
  new: "live-trace",
  investigating: "live-trace",
  escalated_to_vasp: "vasp-identified",
  frozen: "critical",
  closed: "closed",
};

const LABEL_MAP: Record<CaseStatus, string> = {
  "live-trace": "Live Trace",
  "network-signal": "Network Signal",
  "vasp-identified": "VASP Identified",
  critical: "Critical",
  "evidence-ready": "Evidence Ready",
  closed: "Closed",
};

// The backend Case model doesn't carry fraud type / wallet / risk score
// directly — those live on the Wallet/Complaint it's linked to, which this
// list endpoint doesn't join. Rather than fabricate plausible-looking
// values, surface only what the API actually returns and mark the rest
// as genuinely unknown.
function mapCase(c: Case): InvestigationCase {
  return {
    id: `UG-${c.id.slice(0, 8).toUpperCase()}`,
    rawId: c.id,
    fraudType: "Unclassified",
    blockchain: "ETH",
    reportedWallet: "",
    traceStatus: STATUS_MAP[c.status] ?? "live-trace",
    networkSignal: "NONE",
    riskScore: 0,
    victimCount: 0,
    lastActivity: new Date(c.opened_at).toLocaleDateString("en-IN"),
    description: `Case opened by ${c.assigned_investigator ?? "unassigned"}. Status: ${c.status}.`,
  };
}

export function useCases(filterLabel?: string) {
  const [allCases, setAllCases] = useState<InvestigationCase[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    listCases({ page: 1, page_size: 50 })
      .then((data) => {
        if (!cancelled) {
          setAllCases(data.items.map(mapCase));
          setError(null);
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setAllCases([]);
          setError(e instanceof Error ? e.message : "Failed to load cases");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const filtered =
    !filterLabel || filterLabel === "All"
      ? allCases
      : allCases.filter((c) => LABEL_MAP[c.traceStatus] === filterLabel);

  return { cases: filtered, allCases, loading, error };
}
