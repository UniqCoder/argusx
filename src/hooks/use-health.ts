// ============================================================
// useHealth — polls GET /health every 15s.
// Backs every "SYSTEM LIVE" / "LIVE" label in the app — none of them may
// render true without this actually succeeding.
// ============================================================
import { useState, useEffect } from "react";
import { getHealth } from "@/lib/api";
import type { HealthResponse } from "@/lib/api-types";

export function useHealth() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const poll = () => {
      getHealth()
        .then((data) => {
          if (!cancelled) {
            setHealth(data);
            setError(null);
          }
        })
        .catch((e) => {
          if (!cancelled) {
            setHealth(null);
            setError(e instanceof Error ? e.message : "Health check failed");
          }
        });
    };

    poll();
    const id = setInterval(poll, 15000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  const isLive = health?.status === "ok";
  return { health, isLive, error };
}
