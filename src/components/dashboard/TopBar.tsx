import { useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useAlerts } from "@/hooks/use-alerts";
import { useHealth } from "@/hooks/use-health";

function SearchIcon() {
  return (
    <svg
      width="13"
      height="13"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
    >
      <circle cx="7" cy="7" r="4.5" />
      <path d="M10.5 10.5L14 14" />
    </svg>
  );
}

function BellIcon() {
  return (
    <svg
      width="15"
      height="15"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.4"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M8 2a4.5 4.5 0 00-4.5 4.5v3L2 11h12l-1.5-1.5v-3A4.5 4.5 0 008 2zM6.5 11.5a1.5 1.5 0 003 0" />
    </svg>
  );
}

function UserIcon() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.4"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <circle cx="8" cy="5.5" r="2.5" />
      <path d="M2 13.5c0-3 2.7-4.5 6-4.5s6 1.5 6 4.5" />
    </svg>
  );
}

export function TopBar() {
  const [query, setQuery] = useState("");
  const [showNotifs, setShowNotifs] = useState(false);
  const navigate = useNavigate();
  const { events, unreadCount } = useAlerts();
  const { isLive } = useHealth();

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    navigate({ to: "/dashboard/trace", search: { q: query } as never });
  };

  return (
    <header className="ug-topbar">
      {/* Search */}
      <form
        onSubmit={handleSearch}
        className="ug-search"
        style={{ maxWidth: 420 }}
      >
        <SearchIcon />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search wallet address, tx hash, case ID…"
          aria-label="Global intelligence search"
        />
      </form>

      <div style={{ flex: 1 }} />

      {/* System live — reflects a real GET /health poll, not decoration */}
      <div
        className="ug-system-live"
        style={!isLive ? { color: "var(--color-muted-foreground)" } : undefined}
      >
        <span
          className="ug-system-live__dot"
          style={
            !isLive
              ? { background: "var(--color-muted-foreground)", boxShadow: "none" }
              : undefined
          }
        />
        {isLive ? "SYSTEM LIVE" : "SYSTEM OFFLINE"}
      </div>

      {/* Separator */}
      <div
        style={{ width: 1, height: 22, background: "var(--border-strong)" }}
      />

      {/* Notifications */}
      <div style={{ position: "relative" }}>
        <button
          onClick={() => setShowNotifs((v) => !v)}
          style={{
            background: "none",
            border: "none",
            cursor: "pointer",
            color: "var(--color-muted-foreground)",
            padding: "0.3rem",
            borderRadius: "2px",
            display: "flex",
            alignItems: "center",
            position: "relative",
            transition: "color 0.15s",
          }}
          onMouseEnter={(e) =>
            (e.currentTarget.style.color = "var(--color-foreground)")
          }
          onMouseLeave={(e) =>
            (e.currentTarget.style.color = "var(--color-muted-foreground)")
          }
          aria-label="Notifications"
        >
          <BellIcon />
          {unreadCount > 0 && (
            <span
              style={{
                position: "absolute",
                top: 0,
                right: 0,
                width: "6px",
                height: "6px",
                background: "var(--color-signal)",
                boxShadow: "0 0 6px var(--color-signal)",
              }}
            />
          )}
        </button>

        {showNotifs && (
          <div
            style={{
              position: "absolute",
              top: "calc(100% + 8px)",
              right: 0,
              width: 320,
              background: "var(--bg-1)",
              border: "1px solid var(--border-strong)",
              borderRadius: "4px",
              zIndex: 100,
              overflow: "hidden",
              boxShadow: "0 20px 60px oklch(0.04 0.01 258 / 80%)",
            }}
          >
            <div className="ug-panel-header">
              <span className="ug-section-title" style={{ marginBottom: 0 }}>
                Intel Feed
              </span>
              <span
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "0.58rem",
                  color: "var(--color-muted-foreground)",
                }}
              >
                {unreadCount} unread
              </span>
            </div>
            {events.slice(0, 4).map((evt) => {
              const color =
                evt.severity === "CRITICAL"
                  ? "var(--color-signal)"
                  : evt.severity === "HIGH"
                    ? "var(--color-primary)"
                    : evt.severity === "MEDIUM"
                      ? "var(--color-accent)"
                      : "var(--color-muted-foreground)";
              return (
                <div
                  key={evt.id}
                  onClick={() => {
                    navigate({ to: "/dashboard/alerts" });
                    setShowNotifs(false);
                  }}
                  style={{
                    padding: "0.7rem 1rem",
                    borderBottom: "1px solid var(--border-subtle)",
                    cursor: "pointer",
                    background: evt.read
                      ? "transparent"
                      : "oklch(0.83 0.14 205 / 4%)",
                    display: "flex",
                    gap: "0.75rem",
                    alignItems: "flex-start",
                    transition: "background 0.12s",
                  }}
                  onMouseEnter={(e) =>
                    (e.currentTarget.style.background = "oklch(0.98 0 0 / 3%)")
                  }
                  onMouseLeave={(e) =>
                    (e.currentTarget.style.background = evt.read
                      ? "transparent"
                      : "oklch(0.83 0.14 205 / 4%)")
                  }
                >
                  <div
                    style={{
                      width: 2,
                      minHeight: 36,
                      background: color,
                      flexShrink: 0,
                      marginTop: 2,
                    }}
                  />
                  <div>
                    <p
                      style={{
                        fontFamily: "var(--font-mono)",
                        fontSize: "0.56rem",
                        letterSpacing: "0.2em",
                        textTransform: "uppercase",
                        color,
                        marginBottom: "0.2rem",
                      }}
                    >
                      {evt.type}
                    </p>
                    <p
                      style={{
                        fontSize: "0.74rem",
                        color: "var(--color-foreground)",
                        lineHeight: 1.4,
                      }}
                    >
                      {evt.message}
                    </p>
                    <p
                      style={{
                        fontFamily: "var(--font-mono)",
                        fontSize: "0.56rem",
                        color: "var(--color-muted-foreground)",
                        marginTop: "0.2rem",
                      }}
                    >
                      {evt.timestamp}
                    </p>
                  </div>
                </div>
              );
            })}
            <div
              onClick={() => {
                navigate({ to: "/dashboard/alerts" });
                setShowNotifs(false);
              }}
              style={{
                padding: "0.6rem 1rem",
                textAlign: "center",
                fontFamily: "var(--font-mono)",
                fontSize: "0.6rem",
                letterSpacing: "0.16em",
                textTransform: "uppercase",
                color: "var(--color-accent)",
                cursor: "pointer",
                borderTop: "1px solid var(--border-subtle)",
              }}
            >
              View All Alerts
            </div>
          </div>
        )}
      </div>

      {/* Profile */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "0.5rem",
          padding: "0.25rem 0.6rem",
          borderRadius: "2px",
          border: "1px solid var(--border-strong)",
          background: "oklch(0.98 0 0 / 4%)",
          cursor: "pointer",
          transition: "background 0.15s",
        }}
        onMouseEnter={(e) =>
          (e.currentTarget.style.background = "oklch(0.98 0 0 / 8%)")
        }
        onMouseLeave={(e) =>
          (e.currentTarget.style.background = "oklch(0.98 0 0 / 4%)")
        }
      >
        <div
          style={{
            width: 26,
            height: 26,
            borderRadius: "2px",
            background:
              "linear-gradient(135deg, oklch(0.79 0.15 74 / 60%), oklch(0.83 0.14 205 / 60%))",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "var(--color-foreground)",
          }}
        >
          <UserIcon />
        </div>
        <div>
          <p
            style={{
              fontSize: "0.7rem",
              fontWeight: 600,
              color: "var(--color-foreground)",
              lineHeight: 1.2,
            }}
          >
            Investigator
          </p>
          <p
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "0.54rem",
              color: "var(--color-accent)",
              letterSpacing: "0.1em",
            }}
          >
            ACTIVE SESSION
          </p>
        </div>
      </div>
    </header>
  );
}
