/** Mini wallet tracer graph — SVG nodes + edges, amber/cyan palette */
export function WalletTracerMockup() {
  const nodes = [
    { id: "v", x: 50, y: 50, r: 7, color: "#ff3b5c", label: "VICTIM" },
    { id: "w1", x: 110, y: 30, r: 5, color: "#f5a524", label: "0x9f…c4" },
    { id: "w2", x: 110, y: 70, r: 5, color: "#f5a524", label: "0x3a…e1" },
    { id: "m", x: 175, y: 50, r: 6, color: "#a78bfa", label: "MIXER" },
    { id: "w3", x: 235, y: 35, r: 5, color: "#22d3ee", label: "0x7b…f2" },
    { id: "w4", x: 235, y: 65, r: 5, color: "#22d3ee", label: "0x2c…a9" },
    { id: "ex", x: 295, y: 50, r: 7, color: "#34d399", label: "BINANCE" },
  ];
  const edges = [
    ["v", "w1"],
    ["v", "w2"],
    ["w1", "m"],
    ["w2", "m"],
    ["m", "w3"],
    ["m", "w4"],
    ["w3", "ex"],
    ["w4", "ex"],
  ];

  return (
    <div className="ug-mock-wrap">
      <p className="ug-mock-label">WALLET TRACER</p>
      <svg viewBox="0 0 345 100" width="100%" style={{ overflow: "visible" }}>
        <defs>
          <filter id="glow">
            <feGaussianBlur stdDeviation="2" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        {/* edges */}
        {edges.map(([a, b]) => {
          const A = nodes.find((n) => n.id === a)!;
          const B = nodes.find((n) => n.id === b)!;
          return (
            <line
              key={`${a}-${b}`}
              x1={A.x}
              y1={A.y}
              x2={B.x}
              y2={B.y}
              stroke="#22d3ee"
              strokeWidth="0.8"
              strokeOpacity="0.35"
              strokeDasharray="3 2"
            />
          );
        })}
        {/* nodes */}
        {nodes.map((n) => (
          <g key={n.id} filter="url(#glow)">
            <circle
              cx={n.x}
              cy={n.y}
              r={n.r}
              fill={n.color}
              fillOpacity={0.9}
            />
            <circle
              cx={n.x}
              cy={n.y}
              r={n.r + 3}
              fill="none"
              stroke={n.color}
              strokeWidth="0.5"
              strokeOpacity="0.4"
            />
            <text
              x={n.x}
              y={n.y + n.r + 9}
              textAnchor="middle"
              style={{
                fontSize: 5.5,
                fill: "#4a5568",
                fontFamily: "IBM Plex Mono",
              }}
            >
              {n.label}
            </text>
          </g>
        ))}
        {/* path label */}
        <text
          x="172"
          y="92"
          textAnchor="middle"
          style={{
            fontSize: 6,
            fill: "#4a5568",
            fontFamily: "IBM Plex Mono",
            letterSpacing: "0.1em",
          }}
        >
          4 HOPS · 1.42M USDT · TRON
        </text>
      </svg>
      <div className="ug-mock-badge ug-mock-badge--red">HIGH RISK · 0.94</div>
    </div>
  );
}
