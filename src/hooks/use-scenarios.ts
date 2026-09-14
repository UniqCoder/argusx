import { useEffect, useState } from "react";
import { listScenarios } from "@/lib/api";
import type { ScenarioRead } from "@/lib/api-types";

interface ScenariosState {
  scenarios: ScenarioRead[];
  /** False when the backend has the definitions but no case seeded from them. */
  seeded: boolean;
  loading: boolean;
  error: string | null;
}

/**
 * The seeded investigation scenarios, fetched from the backend.
 *
 * Deliberately has no fallback list. If the request fails, or the database has
 * not been seeded, the UI says so — it does not ship its own copy of the cases,
 * which is exactly the arrangement that let the old demo case drift out of sync
 * with every backend feature it was supposed to demonstrate.
 */
export function useScenarios(): ScenariosState {
  const [scenarios, setScenarios] = useState<ScenarioRead[]>([]);
  const [seeded, setSeeded] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    listScenarios()
      .then((res) => {
        if (cancelled) return;
        setScenarios(res.scenarios);
        setSeeded(res.seeded);
        setError(null);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setScenarios([]);
        setSeeded(false);
        setError(e instanceof Error ? e.message : "Could not load scenarios");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return { scenarios, seeded, loading, error };
}
