// ============================================================
// BackendOfflineBanner — visible failure state for a failed API call.
// Extracted from cross-victim.tsx's original inline pattern. The point of
// this component: when a real backend call fails, SAY SO instead of quietly
// swapping in mock data — that silent swap was the actual root cause of
// "every wallet shows the same data."
// ============================================================
interface BackendOfflineBannerProps {
  error: string | null | undefined;
  /** What failed to load, e.g. "trace", "risk score", "correlation". */
  context?: string;
}

export function BackendOfflineBanner({
  error,
  context,
}: BackendOfflineBannerProps) {
  if (!error) return null;

  return (
    <div
      style={{
        padding: "0.6rem 0.85rem",
        background: "oklch(0.64 0.22 18 / 8%)",
        border: "1px solid oklch(0.64 0.22 18 / 30%)",
        borderRadius: "2px",
        fontFamily: "var(--font-mono)",
        fontSize: "0.58rem",
        color: "var(--color-signal)",
        lineHeight: 1.6,
      }}
    >
      Backend unreachable{context ? ` — couldn't load ${context}` : ""}. ({error})
    </div>
  );
}
