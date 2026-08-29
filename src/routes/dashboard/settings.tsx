import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { supabase } from "@/lib/supabase";
import { useNavigate } from "@tanstack/react-router";

export const Route = createFileRoute("/dashboard/settings")({
  component: Settings,
});

function Settings() {
  const [signingOut, setSigningOut] = useState(false);
  const navigate = useNavigate();

  const handleSignOut = async () => {
    setSigningOut(true);
    await supabase.auth.signOut();
    navigate({ to: "/" });
  };

  return (
    <>
      <div className="ug-page-header">
        <p className="ug-page-header__kicker">System</p>
        <h1 className="ug-page-header__title">Settings</h1>
        <p className="ug-page-header__sub">
          Investigator profile and system configuration.
        </p>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: "1.25rem",
          maxWidth: 800,
        }}
      >
        {/* Profile */}
        <div className="ug-surface" style={{ padding: "1.5rem" }}>
          <p className="ug-section-title">Investigator Profile</p>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "1rem",
              marginBottom: "1.25rem",
            }}
          >
            <div
              style={{
                width: 48,
                height: 48,
                borderRadius: "999px",
                background:
                  "linear-gradient(135deg, oklch(0.79 0.15 74 / 60%), oklch(0.83 0.14 205 / 60%))",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: "1.1rem",
              }}
            >
              ðŸ”
            </div>
            <div>
              <p
                style={{
                  fontSize: "0.88rem",
                  fontWeight: 600,
                  color: "var(--color-foreground)",
                }}
              >
                Investigator
              </p>
              <p
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "0.64rem",
                  color: "var(--color-muted-foreground)",
                }}
              >
                Active Session
              </p>
            </div>
          </div>
          <div className="ug-divider" />
          <div>
            {[
              { k: "Role", v: "Senior Investigator" },
              { k: "Unit", v: "Cyber Crime Division" },
              { k: "Clearance", v: "Level 3" },
              { k: "Session", v: "Active" },
            ].map(({ k, v }) => (
              <div key={k} className="ug-data-row">
                <span className="ug-data-row__key">{k}</span>
                <span className="ug-data-row__value">{v}</span>
              </div>
            ))}
          </div>
        </div>

        {/* System */}
        <div className="ug-surface" style={{ padding: "1.5rem" }}>
          <p className="ug-section-title">System Status</p>
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "0.6rem",
              marginBottom: "1.25rem",
            }}
          >
            {[
              { label: "Intelligence Engine", status: "Operational", ok: true },
              { label: "Trace Service", status: "Operational", ok: true },
              {
                label: "Complaint Correlation",
                status: "Operational",
                ok: true,
              },
              { label: "VASP Attribution", status: "Operational", ok: true },
              { label: "Deposit Watch API", status: "Operational", ok: true },
            ].map(({ label, status, ok }) => (
              <div
                key={label}
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                }}
              >
                <span
                  style={{
                    fontSize: "0.78rem",
                    color: "var(--color-foreground)",
                  }}
                >
                  {label}
                </span>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "0.4rem",
                  }}
                >
                  <div
                    style={{
                      width: 6,
                      height: 6,
                      borderRadius: "999px",
                      background: ok
                        ? "var(--color-accent)"
                        : "var(--color-signal)",
                      boxShadow: ok
                        ? "0 0 6px var(--color-accent)"
                        : "0 0 6px var(--color-signal)",
                    }}
                  />
                  <span
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: "0.62rem",
                      color: ok ? "var(--color-accent)" : "var(--color-signal)",
                    }}
                  >
                    {status}
                  </span>
                </div>
              </div>
            ))}
          </div>
          <div className="ug-divider" />
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <div
              style={{
                flex: 1,
                background: "oklch(0.09 0.015 258)",
                border: "1px solid var(--color-border)",
                borderRadius: "0.4rem",
                padding: "0.65rem 0.85rem",
              }}
            >
              <p
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "0.58rem",
                  color: "var(--color-muted-foreground)",
                  marginBottom: "0.15rem",
                }}
              >
                Version
              </p>
              <p
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "0.72rem",
                  color: "var(--color-accent)",
                }}
              >
                2026.08-r4
              </p>
            </div>
            <div
              style={{
                flex: 1,
                background: "oklch(0.09 0.015 258)",
                border: "1px solid var(--color-border)",
                borderRadius: "0.4rem",
                padding: "0.65rem 0.85rem",
              }}
            >
              <p
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "0.58rem",
                  color: "var(--color-muted-foreground)",
                  marginBottom: "0.15rem",
                }}
              >
                Environment
              </p>
              <p
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "0.72rem",
                  color: "var(--color-foreground)",
                }}
              >
                Production
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Sign out */}
      <div style={{ marginTop: "1.5rem", maxWidth: 800 }}>
        <div
          className="ug-surface ug-surface--critical"
          style={{
            padding: "1.25rem",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <div>
            <p
              style={{
                fontSize: "0.84rem",
                fontWeight: 600,
                color: "var(--color-foreground)",
                marginBottom: "0.2rem",
              }}
            >
              End Session
            </p>
            <p
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "0.64rem",
                color: "var(--color-muted-foreground)",
              }}
            >
              Sign out of Argus and return to the landing page.
            </p>
          </div>
          <button
            className="ug-btn-ghost"
            onClick={handleSignOut}
            disabled={signingOut}
            style={{
              borderColor: "oklch(0.64 0.22 18 / 40%)",
              color: "var(--color-signal)",
              flexShrink: 0,
            }}
          >
            {signingOut ? "Signing outâ€¦" : "Sign Out â†’"}
          </button>
        </div>
      </div>
    </>
  );
}
