// ============================================================
// TraceGraph — the money-trail renderer.
//
// Replaces an SVG with a FIXED 980x420 viewBox and no pan/zoom. That was
// measured as the second half of the "graph only shows a few nodes" problem:
// the layout clamped every node into that box, so at 40 nodes 40% of them were
// pinned to the border with centres 14.7px apart (labels need >=68px), and at
// 80 nodes it was a solid clump. Traces now routinely return 50-75 nodes.
//
// So this component: renders the content at its real laid-out size, and lets
// the investigator pan and zoom over it. Nothing is hidden to make the picture
// tidy — if the trace found 75 addresses, 75 addresses are reachable on screen.
//
// All motion is driven by the single timeline in use-trace-timeline.ts, which
// is ordered by the real on-chain time each transfer landed. There are no
// decorative particles and no independent timers: a transfer only animates if
// it is a real transaction in the trace result.
// ============================================================
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { TraceNode, TraceEdge } from "@/lib/mock-data";
import type { TimelineFrame } from "@/hooks/use-trace-timeline";
import { truncateAddress } from "@/lib/address";

// The reported (hop-0 / searched) wallet used to be hardcoded to this same
// red used for confirmed fraudsters and critical terminals — every trace
// target read as "suspected fraudster" at a glance regardless of whether any
// actual evidence (a linked complaint, a sanctions hit) backed that. Most
// traces start from an address that's merely BEING investigated, not one
// already confirmed bad, so it needs its own neutral color; red is reserved
// for when investigation.tsx has real evidence to justify it (see
// `isSuspectedFraudster` in the node color logic below).
const REPORTED_UNCONFIRMED_COLOR = "oklch(0.82 0.14 95)";
const CRITICAL_COLOR = "oklch(0.64 0.22 18)";

const NODE_COLOR: Record<TraceNode["type"], string> = {
  victim: "oklch(0.72 0.024 250)",
  reported: REPORTED_UNCONFIRMED_COLOR,
  intermediate: "oklch(0.83 0.14 205)",
  bridge: "oklch(0.79 0.15 74)",
  mixer: "oklch(0.64 0.22 18)",
  exchange: "oklch(0.79 0.15 74)",
};

// Plain-English type labels shown under every node — a hackathon judge
// should never need to decode a glyph to know what they're looking at.
const TYPE_LABEL: Record<TraceNode["type"], string> = {
  victim: "VICTIM WALLET",
  reported: "REPORTED WALLET",
  intermediate: "INTERMEDIATE",
  bridge: "BRIDGE",
  mixer: "MIXER",
  exchange: "EXCHANGE",
};

const LEGEND_ITEMS: { label: string; color: string }[] = [
  { label: "Victim wallet", color: NODE_COLOR.victim },
  { label: "Reported wallet (under investigation)", color: REPORTED_UNCONFIRMED_COLOR },
  { label: "Suspected fraudster / critical", color: CRITICAL_COLOR },
  { label: "Intermediate", color: NODE_COLOR.intermediate },
  { label: "Exchange / Bridge", color: "oklch(0.79 0.15 74)" },
];

// Terminals that mean "the money is gone / unreachable from here" are drawn
// with a warning weight; terminals that mean "we know exactly where it is" are
// drawn as the payoff. A node's colour is never chosen at random or by index.
const CRITICAL_TERMINALS = new Set([
  "MIXER_BOUNDARY",
  "NODE_LIMIT",
  "EXPLORER_UNAVAILABLE",
]);
const PAYOFF_TERMINALS = new Set(["VASP", "NO_OUTFLOW", "BRIDGE"]);

function nodeGlyph(node: TraceNode): string {
  if (node.isTarget) return "◎";
  if (node.type === "victim") return "!";
  switch (node.terminalKind) {
    case "VASP":
      return "$";
    case "MIXER_BOUNDARY":
      return "≋";
    case "BRIDGE":
      return "⇄";
    case "NO_OUTFLOW":
      return "■";
    case "EXPLORER_UNAVAILABLE":
      return "?";
    case "NODE_LIMIT":
      return "+";
    case "DUST":
    case "DILUTED_OUTFLOW":
      return "·";
    default:
      return "•";
  }
}

interface Props {
  nodes: TraceNode[];
  edges: TraceEdge[];
  frame: TimelineFrame;
  contentWidth: number;
  contentHeight: number;
  selectedId: string | null;
  onSelectNode: (id: string) => void;
  onSelectEdge: (id: string) => void;
}

export function TraceGraph({
  nodes,
  edges,
  frame,
  contentWidth,
  contentHeight,
  selectedId,
  onSelectNode,
  onSelectEdge,
}: Props) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [view, setView] = useState({ x: 0, y: 0, k: 1 });
  const [dragging, setDragging] = useState(false);
  const dragFrom = useRef<{
    x: number;
    y: number;
    vx: number;
    vy: number;
  } | null>(null);

  // Fit the content when a new trace arrives (identity of the node array
  // changes only when the underlying result does).
  const fit = useCallback(() => {
    const el = wrapRef.current;
    if (!el) return;
    const { width, height } = el.getBoundingClientRect();
    if (!width || !height) return;
    const k = Math.min(width / contentWidth, height / contentHeight, 1.4);
    setView({
      x: (width - contentWidth * k) / 2,
      y: (height - contentHeight * k) / 2,
      k,
    });
  }, [contentWidth, contentHeight]);

  useEffect(() => {
    fit();
  }, [fit, nodes]);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => fit());
    ro.observe(el);
    return () => ro.disconnect();
  }, [fit]);

  // React attaches onWheel as a passive listener, so calling
  // preventDefault() through it silently fails (and spams the console with
  // "Unable to preventDefault inside passive event listener invocation")
  // while the page scrolls underneath the graph. A native, explicitly
  // non-passive listener is the only way to actually stop that scroll.
  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const handleWheel = (e: WheelEvent) => {
      e.preventDefault();
      const rect = el.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;
      setView((v) => {
        const k = Math.max(
          0.2,
          Math.min(4, v.k * (e.deltaY < 0 ? 1.12 : 1 / 1.12)),
        );
        // Zoom about the cursor so the thing under the pointer stays put.
        return {
          k,
          x: mx - ((mx - v.x) * k) / v.k,
          y: my - ((my - v.y) * k) / v.k,
        };
      });
    };
    el.addEventListener("wheel", handleWheel, { passive: false });
    return () => el.removeEventListener("wheel", handleWheel);
  }, []);

  const [hoveredId, setHoveredId] = useState<string | null>(null);

  const nodeById = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);
  const active = frame.active;

  // Camera auto-follow: when playback moves to a new transfer, smoothly pan
  // (never zoom — a sudden zoom is what makes an investigator lose their
  // place) so the active edge stays centred, instead of the investigator
  // having to manually chase the money across a wide trace. One tween at a
  // time: a fresh hop cancels whatever tween the previous hop started,
  // rather than stacking rAF loops.
  const followRaf = useRef<number | null>(null);
  const lastFollowedEdgeId = useRef<string | null>(null);
  useEffect(() => {
    const edgeId = active?.step.edgeId ?? null;
    if (!edgeId || edgeId === lastFollowedEdgeId.current || dragging) return;
    lastFollowedEdgeId.current = edgeId;
    const el = wrapRef.current;
    const a = nodeById.get(active!.step.fromId);
    const b = nodeById.get(active!.step.toId);
    if (!el || !a || !b) return;
    const { width, height } = el.getBoundingClientRect();
    if (!width || !height) return;

    const midX = (a.x + b.x) / 2;
    const midY = (a.y + b.y) / 2;
    const k = view.k;
    const targetX = width / 2 - midX * k;
    const targetY = height / 2 - midY * k;
    const startX = view.x;
    const startY = view.y;
    const startTime = performance.now();
    const DURATION = 550;

    if (followRaf.current != null) cancelAnimationFrame(followRaf.current);
    const step = (now: number) => {
      const t = Math.min(1, (now - startTime) / DURATION);
      const eased = 1 - Math.pow(1 - t, 3);
      setView((v) => ({
        ...v,
        x: startX + (targetX - startX) * eased,
        y: startY + (targetY - startY) * eased,
      }));
      followRaf.current = t < 1 ? requestAnimationFrame(step) : null;
    };
    followRaf.current = requestAnimationFrame(step);
    return () => {
      if (followRaf.current != null) cancelAnimationFrame(followRaf.current);
    };
    // Deliberately keyed only on the active edge changing — `view` is read
    // once per hop as the tween's start point, not tracked continuously
    // (that would fight the tween it's driving), and `nodeById` is rebuilt
    // every render so tracking it would refire this every frame instead of
    // once per hop.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active?.step.edgeId, dragging]);

  // After the replay finishes, recentre on the whole trace once — not on
  // every render while paused at the end, and not fighting a manual pan
  // afterwards. Resets the moment playback is scrubbed away from the end.
  const autoFitDone = useRef(false);
  useEffect(() => {
    const complete = frame.stepCount > 0 && frame.stepIndex >= frame.stepCount;
    if (complete && !active && !autoFitDone.current) {
      autoFitDone.current = true;
      fit();
    } else if (!complete) {
      autoFitDone.current = false;
    }
  }, [frame.stepIndex, frame.stepCount, active, fit]);

  const onPointerDown = (e: React.PointerEvent) => {
    if (e.button !== 0) return;
    setDragging(true);
    dragFrom.current = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y };
    (e.target as Element).setPointerCapture?.(e.pointerId);
  };
  const onPointerMove = (e: React.PointerEvent) => {
    const d = dragFrom.current;
    if (!dragging || !d) return;
    setView((v) => ({
      ...v,
      x: d.vx + (e.clientX - d.x),
      y: d.vy + (e.clientY - d.y),
    }));
  };
  const endDrag = () => {
    setDragging(false);
    dragFrom.current = null;
  };

  // What hovering `hoveredId` lights up: itself, its immediate neighbours,
  // and the edges between them. Everything else dims so the eye follows the
  // hovered wallet's actual connections instead of scanning the whole trace.
  const hoverSet = useMemo(() => {
    if (!hoveredId) return null;
    const nodeIds = new Set<string>([hoveredId]);
    const edgeIds = new Set<string>();
    for (const e of edges) {
      if (e.from === hoveredId || e.to === hoveredId) {
        edgeIds.add(e.id);
        nodeIds.add(e.from);
        nodeIds.add(e.to);
      }
    }
    return { nodeIds, edgeIds };
  }, [hoveredId, edges]);
  const hoveredNode = hoveredId ? nodeById.get(hoveredId) : undefined;

  return (
    <div
      ref={wrapRef}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={endDrag}
      onPointerLeave={endDrag}
      style={{
        position: "absolute",
        inset: 0,
        overflow: "hidden",
        cursor: dragging ? "grabbing" : "grab",
        touchAction: "none",
      }}
    >
      <svg width="100%" height="100%" style={{ display: "block" }}>
        <defs>
          <filter id="tg-glow" x="-60%" y="-60%" width="220%" height="220%">
            <feGaussianBlur stdDeviation="3.2" result="b" />
            <feComposite in="SourceGraphic" in2="b" operator="over" />
          </filter>
          <marker
            id="tg-arrow"
            markerWidth="7"
            markerHeight="7"
            refX="6.4"
            refY="3"
            orient="auto"
          >
            <path d="M0 0 L7 3 L0 6 z" fill="oklch(0.83 0.14 205 / 55%)" />
          </marker>
          <marker
            id="tg-arrow-live"
            markerWidth="8"
            markerHeight="8"
            refX="7"
            refY="3.2"
            orient="auto"
          >
            <path d="M0 0 L8 3.2 L0 6.4 z" fill="oklch(0.9 0.17 95)" />
          </marker>
        </defs>

        <g transform={`translate(${view.x},${view.y}) scale(${view.k})`}>
          {/* ── Edges ──────────────────────────────────────────────────── */}
          {edges.map((edge) => {
            const a = nodeById.get(edge.from);
            const b = nodeById.get(edge.to);
            if (!a || !b) return null;
            const drawn = frame.revealedEdges.has(edge.id);
            const isActive = active?.step.edgeId === edge.id;
            if (!drawn && !isActive) return null;

            const isSelected = selectedId === edge.id;
            const len = Math.hypot(b.x - a.x, b.y - a.y) || 1;
            // The active edge draws itself from source to destination as the
            // transfer travels, rather than appearing all at once.
            const shown = isActive ? len * (active?.t ?? 0) : len;
            // A victim/complaint "reported" link is a relationship, not a
            // transaction — drawn distinctly so it never reads as money
            // movement (no arrowhead, no amount, dashed).
            const isReportLink = edge.method === "victim_report";
            // Hovering a wallet lights up its actual connections and dims
            // everything else, so the path reads without inspecting every
            // line individually.
            const dimmed = !!hoverSet && !hoverSet.edgeIds.has(edge.id);

            return (
              <line
                key={edge.id}
                x1={a.x}
                y1={a.y}
                x2={b.x}
                y2={b.y}
                stroke={
                  isReportLink
                    ? "oklch(0.72 0.024 250 / 45%)"
                    : isSelected
                      ? "var(--color-accent)"
                      : isActive
                        ? "oklch(0.9 0.17 95)"
                        : "oklch(0.83 0.14 205 / 32%)"
                }
                strokeWidth={isSelected ? 2.4 : isActive ? 2 : 1.4}
                strokeOpacity={dimmed ? 0.2 : 1}
                strokeDasharray={isReportLink ? "3 3" : `${shown} ${len}`}
                style={{
                  cursor: "pointer",
                  transition: "stroke-opacity 150ms ease",
                }}
                markerEnd={
                  isReportLink
                    ? undefined
                    : isActive
                      ? undefined
                      : isSelected
                        ? "url(#tg-arrow-live)"
                        : "url(#tg-arrow)"
                }
                onClick={(e) => {
                  e.stopPropagation();
                  onSelectEdge(edge.id);
                }}
              />
            );
          })}

          {/* ── The transfer in flight ─────────────────────────────────── */}
          {/* One particle, on one real edge, carrying that transaction's real
              amount. Not a field of decorative dots: this is transfer
              `stepIndex + 1` of `stepCount` in the trace. */}
          {active &&
            (() => {
              const a = nodeById.get(active.step.fromId);
              const b = nodeById.get(active.step.toId);
              if (!a || !b) return null;
              const t = active.t;
              const px = a.x + (b.x - a.x) * t;
              const py = a.y + (b.y - a.y) * t;
              return (
                <g pointerEvents="none">
                  <circle
                    cx={px}
                    cy={py}
                    r={7}
                    fill="oklch(0.9 0.17 95 / 22%)"
                  />
                  <circle
                    cx={px}
                    cy={py}
                    r={3.6}
                    fill="oklch(0.95 0.16 95)"
                    filter="url(#tg-glow)"
                  />
                  <text
                    x={px}
                    y={py - 13}
                    textAnchor="middle"
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: 9.5,
                      fontWeight: 600,
                      fill: "oklch(0.95 0.16 95)",
                    }}
                  >
                    {active.step.amount}
                  </text>
                </g>
              );
            })()}

          {/* ── Nodes ──────────────────────────────────────────────────── */}
          {nodes.map((node) => {
            const revealed = frame.revealedNodes.has(node.id);
            if (!revealed) return null;

            const isSelected = selectedId === node.id;
            const isArriving = frame.arriving.has(node.id);
            const critical = node.terminalKind
              ? CRITICAL_TERMINALS.has(node.terminalKind)
              : false;
            const payoff = node.terminalKind
              ? PAYOFF_TERMINALS.has(node.terminalKind)
              : false;
            // A "reported" node (the trace anchor) only earns the alarming
            // red when something has actually flagged it — a linked
            // complaint or a strong-evidence risk tier (isSuspectedFraudster,
            // set in investigation.tsx). Otherwise it's the neutral
            // "under investigation" color: being traced is not the same as
            // being confirmed a fraudster.
            const color = critical
              ? CRITICAL_COLOR
              : payoff
                ? "oklch(0.79 0.15 74)"
                : node.type === "reported" && !node.isSuspectedFraudster
                  ? REPORTED_UNCONFIRMED_COLOR
                  : node.type === "reported"
                    ? CRITICAL_COLOR
                    : NODE_COLOR[node.type];
            // The searched wallet is the investigation target, not just
            // another hop — it needs to read as visually dominant at a
            // glance, not merely "slightly bigger".
            const isTarget = !!node.isTarget;
            const r = isTarget ? 30 : payoff || critical ? 19 : 16;
            // The moment the trail reaches a real terminal is the payoff of
            // the whole replay — its arrival pulse reads as a bigger, single
            // "hit" rather than the same ambient pulse every other node gets.
            const isClimax = isArriving && (critical || payoff);
            const dimmed = !!hoverSet && !hoverSet.nodeIds.has(node.id);

            return (
              <g
                key={node.id}
                transform={`translate(${node.x},${node.y})`}
                style={{ cursor: "pointer" }}
                onClick={(e) => {
                  e.stopPropagation();
                  onSelectNode(node.id);
                }}
                onMouseEnter={() => setHoveredId(node.id)}
                onMouseLeave={() =>
                  setHoveredId((h) => (h === node.id ? null : h))
                }
              >
                {/* Inner group: the CSS-animated one. The outer `<g>` above
                  owns positioning via the `transform` ATTRIBUTE (translate);
                  this one owns the mount-triggered discovery animation and
                  hover dimming via CSS `transform`/`opacity`, which would
                  otherwise clobber the attribute-based translate if applied
                  on the same element. `transform-origin: 0 0` because every
                  child here is already drawn in local coordinates centred on
                  this node — see the circle/text elements below. */}
                <g
                  style={{
                    transformOrigin: "0 0",
                    opacity: dimmed ? 0.25 : 1,
                    transition: "opacity 150ms ease",
                    animation:
                      "tg-node-in 480ms cubic-bezier(0.34,1.56,0.64,1)",
                  }}
                >
                  {/* Arrival pulse — funds have just landed here. Driven by the
                    timeline, so it marks a real transaction, not a loop. */}
                  {isArriving && (
                    <circle
                      r={isClimax ? r + 14 : r + 10}
                      fill="none"
                      stroke={color}
                      strokeWidth={isClimax ? 1.6 : 1}
                      opacity={0.4}
                    >
                      <animate
                        attributeName="r"
                        from={r}
                        to={isClimax ? r + 22 : r + 16}
                        dur={isClimax ? "0.9s" : "1.1s"}
                        repeatCount="indefinite"
                      />
                      <animate
                        attributeName="opacity"
                        from="0.55"
                        to="0"
                        dur={isClimax ? "0.9s" : "1.1s"}
                        repeatCount="indefinite"
                      />
                    </circle>
                  )}
                  {isSelected && (
                    <circle
                      r={r + 8}
                      fill="none"
                      stroke="var(--color-accent)"
                      strokeWidth={1.5}
                      opacity={0.6}
                    />
                  )}
                  {/* A standing ring on the target, always on — not just on
                    hover/selection — so it reads as the anchor of the whole
                    graph even in a busy trace. */}
                  {isTarget && (
                    <circle
                      r={r + 9}
                      fill="none"
                      stroke={color}
                      strokeWidth={1}
                      strokeDasharray="2 4"
                      opacity={0.5}
                    />
                  )}
                  <circle
                    r={r}
                    fill={color.replace(")", " / 14%)")}
                    stroke={color}
                    strokeWidth={isTarget ? 2.5 : 1.5}
                    filter={
                      isSelected || isArriving || isTarget
                        ? "url(#tg-glow)"
                        : undefined
                    }
                  />
                  <text
                    y={4.5}
                    textAnchor="middle"
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: 11,
                      fontWeight: 700,
                      fill: color,
                      pointerEvents: "none",
                    }}
                  >
                    {nodeGlyph(node)}
                  </text>
                  <text
                    y={r + 14}
                    textAnchor="middle"
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: 8.5,
                      fontWeight: 700,
                      fill: "var(--color-foreground)",
                      letterSpacing: "0.04em",
                      pointerEvents: "none",
                    }}
                  >
                    {node.label}
                  </text>
                  {/* Plain-English type — the thing a first-time viewer needs
                    to know before the glyph or the address. */}
                  <text
                    y={r + 25}
                    textAnchor="middle"
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: 7,
                      fontWeight: 700,
                      fill: color,
                      letterSpacing: "0.1em",
                      pointerEvents: "none",
                    }}
                  >
                    {node.isTarget
                      ? node.isSuspectedFraudster
                        ? "SUSPECTED FRAUDSTER"
                        : "REPORTED — FUNDS SENT HERE"
                      : critical
                        ? "CRITICAL TERMINAL"
                        : payoff
                          ? "TRACED TO EXCHANGE"
                          : TYPE_LABEL[node.type]}
                  </text>
                  <text
                    y={r + 36}
                    textAnchor="middle"
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: 7.5,
                      fill: "var(--color-muted-foreground)",
                      pointerEvents: "none",
                    }}
                  >
                    {truncateAddress(node.address)}
                  </text>
                </g>
              </g>
            );
          })}
        </g>
      </svg>

      {/* Hover tooltip — only real fields, and only while genuinely hovering
          (not a hint that lingers or reappears from stale state). Positioned
          in screen space from the node's content coordinates + the current
          pan/zoom, since the node itself lives inside the transformed SVG
          group. */}
      {hoveredNode && (
        <div
          style={{
            position: "absolute",
            left: hoveredNode.x * view.k + view.x,
            top: hoveredNode.y * view.k + view.y - 90,
            transform: "translateX(-50%)",
            padding: "0.5rem 0.65rem",
            background: "var(--bg-1)",
            border: "1px solid var(--border-strong)",
            borderRadius: 2,
            boxShadow: "0 8px 24px oklch(0.04 0.01 258 / 60%)",
            pointerEvents: "none",
            zIndex: 10,
            minWidth: 140,
          }}
        >
          {[
            {
              k: "Type",
              v: hoveredNode.isSuspectedFraudster
                ? "SUSPECTED FRAUDSTER"
                : hoveredNode.isTarget
                  ? "SEARCHED WALLET"
                  : TYPE_LABEL[hoveredNode.type],
            },
            { k: "Address", v: truncateAddress(hoveredNode.address, 10, 6) },
            { k: "Value", v: hoveredNode.amount ?? "—" },
            {
              k: "Risk",
              v:
                hoveredNode.riskScore != null
                  ? `${hoveredNode.riskScore}`
                  : "—",
            },
          ].map(({ k, v }) => (
            <div
              key={k}
              style={{
                display: "flex",
                justifyContent: "space-between",
                gap: "0.75rem",
              }}
            >
              <span
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "0.54rem",
                  letterSpacing: "0.12em",
                  textTransform: "uppercase",
                  color: "var(--color-muted-foreground)",
                }}
              >
                {k}
              </span>
              <span
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "0.6rem",
                  color: "var(--color-foreground)",
                }}
              >
                {v}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Legend — what each colour means, so a viewer never has to guess. */}
      <div
        style={{
          position: "absolute",
          top: 10,
          left: 10,
          display: "flex",
          flexDirection: "column",
          gap: 3,
          padding: "0.4rem 0.55rem",
          background: "var(--bg-2)",
          border: "1px solid var(--border-strong)",
          borderRadius: 2,
          pointerEvents: "none",
        }}
      >
        {LEGEND_ITEMS.map((item) => (
          <div
            key={item.label}
            style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}
          >
            <span
              style={{
                width: 7,
                height: 7,
                borderRadius: "50%",
                background: item.color,
                flexShrink: 0,
              }}
            />
            <span
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "0.56rem",
                color: "var(--color-muted-foreground)",
                letterSpacing: "0.04em",
              }}
            >
              {item.label}
            </span>
          </div>
        ))}
      </div>

      {/* Zoom affordances — a graph you cannot navigate is a graph that hides
          data, which is the failure mode this component exists to fix. */}
      <div
        style={{
          position: "absolute",
          bottom: 10,
          right: 10,
          display: "flex",
          gap: 4,
        }}
      >
        {[
          {
            label: "−",
            act: () => setView((v) => ({ ...v, k: Math.max(0.2, v.k / 1.25) })),
          },
          { label: "Fit", act: fit },
          {
            label: "+",
            act: () => setView((v) => ({ ...v, k: Math.min(4, v.k * 1.25) })),
          },
        ].map((b) => (
          <button
            key={b.label}
            onClick={b.act}
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "0.62rem",
              padding: "0.2rem 0.5rem",
              background: "var(--bg-2)",
              border: "1px solid var(--border-strong)",
              borderRadius: 2,
              color: "var(--color-muted-foreground)",
              cursor: "pointer",
            }}
          >
            {b.label}
          </button>
        ))}
      </div>
      <div
        style={{
          position: "absolute",
          bottom: 12,
          left: 12,
          fontFamily: "var(--font-mono)",
          fontSize: "0.56rem",
          color: "var(--color-muted-foreground)",
          opacity: 0.75,
          pointerEvents: "none",
        }}
      >
        drag to pan · scroll to zoom · {Math.round(view.k * 100)}%
      </div>
    </div>
  );
}
