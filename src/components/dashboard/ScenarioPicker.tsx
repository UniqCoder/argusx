import { useState } from "react";
import { useScenarios } from "@/hooks/use-scenarios";
import { chainLabel } from "@/lib/chains";
import type { ScenarioRead } from "@/lib/api-types";

const MONO = "var(--font-mono, ui-monospace, monospace)";

function formatInr(amount: number): string {
  if (amount >= 10_000_000) return `₹${(amount / 10_000_000).toFixed(2)} Cr`;
  if (amount >= 100_000) return `₹${(amount / 100_000).toFixed(2)} L`;
  return `₹${amount.toLocaleString("en-IN")}`;
}

/**
 * The seeded investigation scenarios, listed by the backend.
 *
 * This replaces a hardcoded "load demo case" button that pointed at a frontend
 * fixture and bypassed the API entirely. Selecting one here sets the active
 * wallet and navigates — exactly what pasting an address does — so the trace
 * that follows is a real trace through the real engine. The only difference is
 * which explorer answers for those addresses.
 */
export function ScenarioPicker({
  onLoad,
}: {
  onLoad: (scenario: ScenarioRead) => void;
}) {
  const { scenarios, seeded, loading, error } = useScenarios();
  const [expanded, setExpanded] = useState<string | null>(null);

  return (
    <div
      className="ug-surface"
      style={{
        overflow: "hidden",
        marginBottom: "0.75rem",
        border: "1px solid oklch(0.79 0.15 74 / 35%)",
      }}
    >
      <div className="ug-panel-header">
        <span className="ug-section-title" style={{ marginBottom: 0 }}>
          Investigation Scenarios
        </span>
        <span
          className="ug-badge"
          style={{
            fontSize: "0.55rem",
            background: "oklch(0.79 0.15 74 / 16%)",
            color: "var(--color-primary)",
            border: "1px solid oklch(0.79 0.15 74 / 40%)",
          }}
        >
          SEEDED
        </span>
      </div>

      <div style={{ padding: "1rem" }}>
        <p
          style={{
            fontSize: "0.72rem",
            color: "var(--color-muted-foreground)",
            lineHeight: 1.65,
            marginBottom: "0.9rem",
          }}
        >
          Five cases with synthetic addresses and transactions, seeded into the
          database and traced by the <strong>real engine</strong> — the same
          taint propagation, terminal classification and evidence ledger a live
          wallet gets. They exist because a live wallet cannot be relied on to
          pass through a mixer, a bridge and an exchange on cue, or to carry
          three separate victim complaints.
        </p>

        {loading && (
          <p style={{ fontFamily: MONO, fontSize: "0.66rem", color: "var(--color-muted-foreground)" }}>
            Loading scenarios…
          </p>
        )}

        {error && (
          <div
            style={{
              padding: "0.7rem 0.8rem",
              border: "1px solid oklch(0.64 0.22 18 / 40%)",
              background: "oklch(0.64 0.22 18 / 10%)",
              borderRadius: 2,
              fontSize: "0.7rem",
              color: "var(--color-muted-foreground)",
              lineHeight: 1.6,
            }}
          >
            Could not reach the scenarios endpoint — {error}
          </div>
        )}

        {!loading && !error && !seeded && (
          <div
            style={{
              padding: "0.75rem 0.85rem",
              border: "1px solid oklch(0.79 0.15 74 / 35%)",
              background: "oklch(0.79 0.15 74 / 8%)",
              borderRadius: 2,
              fontSize: "0.7rem",
              color: "var(--color-muted-foreground)",
              lineHeight: 1.7,
            }}
          >
            These scenarios are defined but have not been seeded into this
            database, so tracing one would return nothing. Seed them with:
            <code
              style={{
                display: "block",
                marginTop: "0.5rem",
                fontFamily: MONO,
                fontSize: "0.64rem",
                color: "var(--color-primary)",
                wordBreak: "break-all",
              }}
            >
              docker exec argus_dev_backend python -m scripts.reset_demo_data
            </code>
          </div>
        )}

        {!loading &&
          !error &&
          scenarios.map((s) => {
            const isOpen = expanded === s.key;
            const ready = !!s.case_id;
            return (
              <div
                key={s.key}
                style={{
                  border: "1px solid var(--color-border)",
                  borderRadius: 2,
                  marginBottom: "0.55rem",
                  opacity: ready ? 1 : 0.55,
                }}
              >
                <button
                  onClick={() => setExpanded(isOpen ? null : s.key)}
                  style={{
                    width: "100%",
                    display: "block",
                    textAlign: "left",
                    padding: "0.7rem 0.8rem",
                    background: "transparent",
                    border: "none",
                    cursor: "pointer",
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      alignItems: "baseline",
                      justifyContent: "space-between",
                      gap: "0.6rem",
                      marginBottom: "0.3rem",
                    }}
                  >
                    <span
                      style={{
                        fontSize: "0.8rem",
                        fontWeight: 600,
                        color: "var(--color-foreground)",
                      }}
                    >
                      {s.title}
                    </span>
                    <span
                      style={{
                        fontFamily: MONO,
                        fontSize: "0.6rem",
                        color: "var(--color-primary)",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {formatInr(s.victim_amount_inr)}
                    </span>
                  </div>

                  <p
                    style={{
                      fontSize: "0.68rem",
                      color: "var(--color-muted-foreground)",
                      lineHeight: 1.5,
                      marginBottom: "0.45rem",
                    }}
                  >
                    {s.subtitle}
                  </p>

                  <div style={{ display: "flex", gap: "0.3rem", flexWrap: "wrap" }}>
                    {s.chains.map((c) => (
                      <span
                        key={c}
                        style={{
                          fontFamily: MONO,
                          fontSize: "0.55rem",
                          letterSpacing: "0.08em",
                          padding: "0.1rem 0.35rem",
                          borderRadius: 2,
                          background: "oklch(0.98 0 0 / 5%)",
                          color: "var(--color-muted-foreground)",
                        }}
                      >
                        {chainLabel(c).toUpperCase()}
                      </span>
                    ))}
                    <span
                      style={{
                        fontFamily: MONO,
                        fontSize: "0.55rem",
                        letterSpacing: "0.08em",
                        padding: "0.1rem 0.35rem",
                        borderRadius: 2,
                        background: "oklch(0.98 0 0 / 5%)",
                        color: "var(--color-muted-foreground)",
                      }}
                    >
                      {s.complaint_count} COMPLAINT
                      {s.complaint_count === 1 ? "" : "S"}
                    </span>
                  </div>
                </button>

                {isOpen && (
                  <div
                    style={{
                      padding: "0 0.8rem 0.8rem",
                      borderTop: "1px solid var(--color-border)",
                      paddingTop: "0.7rem",
                    }}
                  >
                    <p
                      style={{
                        fontSize: "0.7rem",
                        color: "var(--color-muted-foreground)",
                        lineHeight: 1.65,
                        marginBottom: "0.6rem",
                      }}
                    >
                      {s.headline}
                    </p>

                    <p
                      style={{
                        fontFamily: MONO,
                        fontSize: "0.55rem",
                        letterSpacing: "0.1em",
                        textTransform: "uppercase",
                        color: "var(--color-muted-foreground)",
                        marginBottom: "0.35rem",
                      }}
                    >
                      Demonstrates
                    </p>
                    <ul
                      style={{
                        listStyle: "none",
                        padding: 0,
                        margin: "0 0 0.7rem",
                      }}
                    >
                      {s.demonstrates.map((d) => (
                        <li
                          key={d}
                          style={{
                            fontSize: "0.68rem",
                            color: "var(--color-muted-foreground)",
                            lineHeight: 1.6,
                            paddingLeft: "0.8rem",
                            position: "relative",
                          }}
                        >
                          <span
                            style={{
                              position: "absolute",
                              left: 0,
                              color: "var(--color-primary)",
                            }}
                          >
                            ·
                          </span>
                          {d}
                        </li>
                      ))}
                    </ul>

                    <p
                      style={{
                        fontFamily: MONO,
                        fontSize: "0.58rem",
                        color: "var(--color-muted-foreground)",
                        wordBreak: "break-all",
                        marginBottom: "0.6rem",
                      }}
                    >
                      {s.anchor_address}
                    </p>

                    <button
                      onClick={() => onLoad(s)}
                      disabled={!ready}
                      className="ug-btn-ghost"
                      style={{
                        width: "100%",
                        justifyContent: "center",
                        fontSize: "0.7rem",
                        padding: "0.55rem",
                        borderRadius: 2,
                        borderColor: "oklch(0.79 0.15 74 / 45%)",
                        color: "var(--color-primary)",
                        cursor: ready ? "pointer" : "not-allowed",
                      }}
                    >
                      {ready ? "TRACE THIS CASE →" : "NOT SEEDED"}
                    </button>
                  </div>
                )}
              </div>
            );
          })}
      </div>
    </div>
  );
}
