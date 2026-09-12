import { useCaseContext } from "@/store/case-context-store";
import { useCases } from "@/hooks/use-cases";
import { useState } from "react";

export function CaseSelector() {
  const { activeCaseId, activeCaseNumber, setActiveCaseMeta } =
    useCaseContext();
  const { allCases, loading } = useCases();
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div style={{ position: "relative" }}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        style={{
          padding: "0.5rem 0.75rem",
          background: "var(--bg-2)",
          border: "1px solid var(--border-strong)",
          borderRadius: "2px",
          fontFamily: "var(--font-mono)",
          fontSize: "0.65rem",
          color: "var(--color-accent)",
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
          gap: "0.4rem",
          whiteSpace: "nowrap",
        }}
      >
        <span>{activeCaseId ? activeCaseNumber : "Select case"}</span>
        <span style={{ fontSize: "0.5rem" }}>▼</span>
      </button>

      {isOpen && (
        <div
          style={{
            position: "absolute",
            top: "100%",
            left: 0,
            background: "var(--bg-0)",
            border: "1px solid var(--border-strong)",
            borderRadius: "2px",
            marginTop: "0.25rem",
            minWidth: "200px",
            maxHeight: "300px",
            overflowY: "auto",
            zIndex: 50,
            boxShadow: "0 4px 12px rgba(0,0,0,0.15)",
          }}
        >
          {loading && (
            <p
              style={{
                padding: "0.65rem 0.75rem",
                fontFamily: "var(--font-mono)",
                fontSize: "0.6rem",
                color: "var(--color-muted-foreground)",
              }}
            >
              Loading cases…
            </p>
          )}
          {!loading && allCases.length === 0 && (
            <p
              style={{
                padding: "0.65rem 0.75rem",
                fontFamily: "var(--font-mono)",
                fontSize: "0.6rem",
                color: "var(--color-muted-foreground)",
                maxWidth: 220,
              }}
            >
              No cases yet.
            </p>
          )}
          {allCases.map((caseItem) => (
            <button
              key={caseItem.id}
              onClick={() => {
                setActiveCaseMeta({
                  caseId: caseItem.rawId,
                  caseNumber: caseItem.id,
                  status: caseItem.traceStatus,
                });
                setIsOpen(false);
              }}
              style={{
                width: "100%",
                padding: "0.5rem 0.75rem",
                textAlign: "left",
                background:
                  activeCaseId === caseItem.id
                    ? "oklch(0.83 0.14 205 / 8%)"
                    : "transparent",
                border: "none",
                borderBottom: "1px solid var(--border-subtle)",
                fontFamily: "var(--font-mono)",
                fontSize: "0.6rem",
                color:
                  activeCaseId === caseItem.id
                    ? "var(--color-accent)"
                    : "var(--color-muted-foreground)",
                cursor: "pointer",
                transition: "all 0.12s",
              }}
              onMouseEnter={(e) => {
                if (activeCaseId !== caseItem.id) {
                  e.currentTarget.style.background = "oklch(0.98 0 0 / 2%)";
                  e.currentTarget.style.color = "var(--color-foreground)";
                }
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background =
                  activeCaseId === caseItem.id
                    ? "oklch(0.83 0.14 205 / 8%)"
                    : "transparent";
                e.currentTarget.style.color =
                  activeCaseId === caseItem.id
                    ? "var(--color-accent)"
                    : "var(--color-muted-foreground)";
              }}
            >
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                }}
              >
                <span>{caseItem.id}</span>
                <span style={{ fontSize: "0.55rem", opacity: 0.6 }}>
                  {caseItem.traceStatus}
                </span>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
