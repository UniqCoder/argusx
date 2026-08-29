// ============================================================
// useCases — fetches GET /api/v1/cases
// Falls back to MOCK_CASES when backend unreachable.
// ============================================================
import { useState, useEffect } from "react";
import { listCases } from "@/lib/api";
import type { Case, CaseStatus as ApiStatus } from "@/lib/api-types";
import {
  MOCK_CASES,
  type InvestigationCase,
  type CaseStatus,
} from "@/lib/mock-data";

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

function mapCase(c: Case, i: number): InvestigationCase {
  return {
    id: `UG-${c.id.slice(0, 8).toUpperCase()}`,
    fraudType: "Investment Scam",
    blockchain: "ETH",
    reportedWallet: "0x" + c.id.replace(/-/g, "").slice(0, 8) + "...",
    traceStatus: STATUS_MAP[c.status] ?? "live-trace",
    networkSignal: i % 3 === 0 ? "HIGH" : i % 3 === 1 ? "MEDIUM" : "NONE",
    riskScore: Math.max(40, 95 - i * 7),
    victimCount: Math.max(1, 5 - i),
    lastActivity: new Date(c.opened_at).toLocaleDateString("en-IN"),
    description: `Case opened by ${c.assigned_investigator ?? "unassigned"}. Status: ${c.status}.`,
  };
}

export function useCases(filterLabel?: string) {
  const [allCases, setAllCases] = useState<InvestigationCase[]>(MOCK_CASES);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    listCases({ page: 1, page_size: 50 })
      .then((data) => {
        if (!cancelled) {
          setAllCases(
            data.items.length > 0 ? data.items.map(mapCase) : MOCK_CASES,
          );
          setError(null);
        }
      })
      .catch((e) => {
        if (!cancelled)
          setError(e instanceof Error ? e.message : "Failed to load cases");
        // MOCK_CASES already set as initial state
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
