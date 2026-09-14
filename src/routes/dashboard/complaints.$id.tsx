import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { getComplaint } from "@/lib/api";
import { useCaseContext } from "@/store/case-context-store";
import type { ComplaintDetail } from "@/lib/api-types";

export const Route = createFileRoute("/dashboard/complaints/$id")({
  component: ComplaintDetailPage,
});

const MONO = "var(--font-mono)";

/**
 * The complaint a Cross-Victim row names, opened directly.
 *
 * Previously clicking a linked complaint discarded its id and only reused
 * the wallet already on screen — this route exists so that action is real:
 * the actual complaint, its narrative and its extracted entities.
 */
function ComplaintDetailPage() {
  const { id } = Route.useParams();
  const navigate = useNavigate();
  const { setActiveWallet } = useCaseContext();
  const [complaint, setComplaint] = useState<ComplaintDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getComplaint(id)
      .then((c) => {
        if (!cancelled) setComplaint(c);
      })
      .catch((e) => {
        if (!cancelled)
          setError(e instanceof Error ? e.message : "Could not load complaint");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  return (
    <div style={{ maxWidth: 760, margin: "0 auto" }}>
      <div className="ug-page-header" style={{ justifyContent: "flex-start" }}>
        <div className="ug-page-header__left">
          <p className="ug-page-header__kicker">Complaint</p>
          <h1 className="ug-page-header__title">
            {complaint?.ncrp_ref ?? id.slice(0, 8).toUpperCase()}
          </h1>
        </div>
      </div>

      {loading && (
        <p style={{ fontFamily: MONO, fontSize: "0.7rem", color: "var(--color-muted-foreground)" }}>
          Loading…
        </p>
      )}

      {error && (
        <div
          style={{
            padding: "0.85rem 1rem", borderRadius: 2,
            border: "1px solid oklch(0.64 0.22 18 / 40%)",
            background: "oklch(0.64 0.22 18 / 10%)",
            fontSize: "0.72rem", color: "var(--color-muted-foreground)",
          }}
        >
          {error}
        </div>
      )}

      {complaint && (
        <div className="ug-surface" style={{ padding: "1.25rem" }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.85rem", marginBottom: "1rem" }}>
            <Field label="Source" value={complaint.source_platform.toUpperCase()} />
            <Field label="Fraud typology" value={complaint.fraud_typology ?? "—"} />
            <Field label="Filed" value={new Date(complaint.filed_at).toLocaleString()} />
            <Field label="Amount lost" value={complaint.amount_lost ? `₹${complaint.amount_lost.toLocaleString("en-IN")}` : "—"} />
            <Field label="State" value={complaint.state ?? "—"} />
            <Field label="District" value={complaint.district ?? "—"} />
          </div>

          {complaint.narrative_text && (
            <>
              <p style={{ fontFamily: MONO, fontSize: "0.58rem", letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--color-muted-foreground)", marginBottom: "0.35rem" }}>
                Narrative
              </p>
              <p style={{ fontSize: "0.78rem", lineHeight: 1.7, color: "var(--color-foreground)", marginBottom: "1rem" }}>
                {complaint.narrative_text}
              </p>
            </>
          )}

          {complaint.extracted_entities?.crypto_addresses?.length ? (
            <>
              <p style={{ fontFamily: MONO, fontSize: "0.58rem", letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--color-muted-foreground)", marginBottom: "0.35rem" }}>
                Wallets named
              </p>
              <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem", marginBottom: "1rem" }}>
                {complaint.extracted_entities.crypto_addresses.map((w) => (
                  <button
                    key={w.address}
                    onClick={() => {
                      setActiveWallet(w.address, w.chain as any);
                      navigate({ to: "/dashboard/investigation" });
                    }}
                    className="ug-btn-ghost"
                    style={{ fontFamily: MONO, fontSize: "0.68rem", justifyContent: "flex-start", padding: "0.5rem 0.7rem" }}
                  >
                    {w.chain} · {w.address}
                  </button>
                ))}
              </div>
            </>
          ) : null}
        </div>
      )}
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p style={{ fontFamily: MONO, fontSize: "0.56rem", letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--color-muted-foreground)", marginBottom: "0.2rem" }}>
        {label}
      </p>
      <p style={{ fontSize: "0.78rem", color: "var(--color-foreground)" }}>{value}</p>
    </div>
  );
}
