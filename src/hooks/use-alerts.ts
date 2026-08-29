// ============================================================
// useAlerts — polls GET /api/v1/alerts every 5 seconds
// Falls back to MOCK_EVENTS when backend unreachable.
// ============================================================
import { useState, useEffect } from "react";
import { listAlerts } from "@/lib/api";
import type { Alert } from "@/lib/api-types";
import { MOCK_EVENTS, type IntelEvent } from "@/lib/mock-data";

const SEV_MAP: Record<string, IntelEvent["severity"]> = {
  block: "CRITICAL",
  hold: "HIGH",
  allow: "INFO",
};

const TYPE_MAP: Record<string, string> = {
  check_wallet_hook: "DEPOSIT ALERT",
  registry_refresh: "REGISTRY UPDATE",
  manual: "MANUAL ALERT",
};

function mapAlert(a: Alert): IntelEvent {
  return {
    id: a.id,
    severity: SEV_MAP[a.action] ?? "INFO",
    type: TYPE_MAP[a.triggered_by] ?? "ALERT",
    message: `Wallet flagged — action: ${a.action.toUpperCase()}. Triggered by ${a.triggered_by.replace(/_/g, " ")}.`,
    wallet: a.wallet_id.slice(0, 8) + "...",
    caseId: a.case_id ?? "",
    timestamp: new Date(a.created_at).toLocaleTimeString(),
    read: a.resolved_at !== null,
  };
}

export function useAlerts() {
  const [events, setEvents] = useState<IntelEvent[]>(MOCK_EVENTS);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const fetchAlerts = async () => {
      try {
        const data = await listAlerts({ resolved: false });
        if (!cancelled) {
          setEvents(
            data.items.length > 0 ? data.items.map(mapAlert) : MOCK_EVENTS,
          );
          setError(null);
        }
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Failed to load alerts");
          // Keep current events (mock data) on error — don't blank the feed
        }
      }
    };

    fetchAlerts();
    const id = setInterval(fetchAlerts, 5000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  const unreadCount = events.filter((e) => !e.read).length;
  return { events, setEvents, unreadCount, error };
}
