/** Risk score panel — gauge arc + SHAP evidence bars */
export function RiskScoreMockup() {
  const score = 0.94;
  const R = 38,
    cx = 60,
    cy = 58;
  const startAngle = -210,
    endAngle = 30; // degrees, 240° arc
  const range = endAngle - startAngle;
  const filled = startAngle + range * score;
  const toRad = (d: number) => (d * Math.PI) / 180;
  const arcPath = (from: number, to: number, r: number) => {
    const s = {
      x: cx + r * Math.cos(toRad(from)),
      y: cy + r * Math.sin(toRad(from)),
    };
    const e = {
      x: cx + r * Math.cos(toRad(to)),
      y: cy + r * Math.sin(toRad(to)),
    };
    const large = to - from > 180 ? 1 : 0;
    return `M ${s.x} ${s.y} A ${r} ${r} 0 ${large} 1 ${e.x} ${e.y}`;
  };

  const shap = [
    { label: "fan_in_count", val: 0.82, dir: "↑", color: "#ff3b5c" },
    { label: "cross_victim_corr", val: 0.67, dir: "↑", color: "#f5a524" },
    { label: "wallet_age_days", val: 0.24, dir: "↓", color: "#22d3ee" },
  ];

  return (
    <div className="ug-mock-wrap">
      <p className="ug-mock-label">RISK SCORE PANEL</p>
      <div style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
        {/* Gauge */}
        <svg width="120" height="72" viewBox="0 0 120 72">
          <path
            d={arcPath(startAngle, endAngle, R)}
            fill="none"
            stroke="#1a2a44"
            strokeWidth="6"
            strokeLinecap="round"
          />
          <path
            d={arcPath(startAngle, filled, R)}
            fill="none"
            stroke="#ff3b5c"
            strokeWidth="6"
            strokeLinecap="round"
            style={{ filter: "drop-shadow(0 0 6px #ff3b5c88)" }}
          />
          <text
            x={cx}
            y={cy - 4}
            textAnchor="middle"
            style={{
              fontSize: 18,
              fontFamily: "IBM Plex Mono",
              fill: "#ff3b5c",
              fontWeight: 700,
            }}
          >
            {Math.round(score * 100)}
          </text>
          <text
            x={cx}
            y={cy + 9}
            textAnchor="middle"
            style={{
              fontSize: 6,
              fontFamily: "IBM Plex Mono",
              fill: "#4a5568",
              letterSpacing: "0.1em",
            }}
          >
            CRITICAL
          </text>
        </svg>
        {/* SHAP bars */}
        <div
          style={{
            flex: 1,
            paddingTop: 4,
            display: "flex",
            flexDirection: "column",
            gap: 7,
          }}
        >
          {shap.map((s) => (
            <div key={s.label}>
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  marginBottom: 2,
                }}
              >
                <span
                  style={{
                    fontSize: 7,
                    fontFamily: "IBM Plex Mono",
                    color: "#4a5568",
                    letterSpacing: "0.06em",
                  }}
                >
                  {s.label}
                </span>
                <span
                  style={{
                    fontSize: 7,
                    fontFamily: "IBM Plex Mono",
                    color: s.color,
                  }}
                >
                  {s.dir}
                </span>
              </div>
              <div
                style={{
                  height: 4,
                  background: "#1a2a44",
                  borderRadius: 2,
                  overflow: "hidden",
                }}
              >
                <div
                  style={{
                    width: `${s.val * 100}%`,
                    height: "100%",
                    background: s.color,
                    borderRadius: 2,
                    boxShadow: `0 0 6px ${s.color}66`,
                  }}
                />
              </div>
            </div>
          ))}
        </div>
      </div>
      <div
        className="ug-mock-badge ug-mock-badge--red"
        style={{ marginTop: 8 }}
      >
        FREEZE RECOMMENDED
      </div>
    </div>
  );
}
