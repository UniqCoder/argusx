// ============================================================
// useForceLayout — computes real node positions for the trace graph.
// TraceGraph (investigation.tsx) reads node.x/node.y directly and does no
// layout itself, so this hook is the only thing standing between "flat list
// of hops" and "a graph that actually reflects which wallets connect to
// which." Runs the simulation to convergence once per new node/edge set
// (not a live animated loop — that would fight TraceGraph's own particle
// requestAnimationFrame loop for frame budget) and clamps to the SVG's
// existing 980x420 viewBox since TraceGraph has no pan/zoom.
// ============================================================
import { useMemo } from "react";
import {
  forceSimulation,
  forceLink,
  forceManyBody,
  forceCollide,
  forceX,
  forceY,
  type SimulationNodeDatum,
} from "d3-force";
import type { TraceNode, TraceEdge } from "@/lib/mock-data";

const VIEW_W = 980;
const VIEW_H = 420;
const PADDING = 70;
const TICKS = 300;

type SimNode = SimulationNodeDatum & { id: string };

export function useForceLayout(
  nodes: TraceNode[],
  edges: TraceEdge[],
): TraceNode[] {
  return useMemo(() => {
    if (nodes.length === 0) return nodes;
    if (nodes.length === 1) {
      const only = nodes[0];
      return only ? [{ ...only, x: VIEW_W / 2, y: VIEW_H / 2 }] : nodes;
    }

    const simNodes: SimNode[] = nodes.map((n) => ({ id: n.id }));
    const simLinks = edges
      .filter(
        (e) =>
          nodes.some((n) => n.id === e.from) &&
          nodes.some((n) => n.id === e.to),
      )
      .map((e) => ({ source: e.from, target: e.to }));

    const simulation = forceSimulation(simNodes)
      .force(
        "link",
        forceLink<SimNode, { source: string; target: string }>(simLinks)
          .id((d) => d.id)
          .distance(120),
      )
      .force("charge", forceManyBody().strength(-260))
      .force("collide", forceCollide(44))
      .force("x", forceX(VIEW_W / 2).strength(0.06))
      .force("y", forceY(VIEW_H / 2).strength(0.08))
      .stop();

    for (let i = 0; i < TICKS; i++) simulation.tick();

    const positioned = new Map(
      simNodes.map((n) => [
        n.id,
        {
          x: Math.min(VIEW_W - PADDING, Math.max(PADDING, n.x ?? VIEW_W / 2)),
          y: Math.min(VIEW_H - PADDING, Math.max(PADDING, n.y ?? VIEW_H / 2)),
        },
      ]),
    );

    return nodes.map((n) => {
      const pos = positioned.get(n.id);
      return pos ? { ...n, x: pos.x, y: pos.y } : n;
    });
  }, [nodes, edges]);
}
