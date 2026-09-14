// ============================================================
// useTraceTimeline — the single animation controller for the money trail.
//
// Why one controller: the reveal used to be a bare `progress` number times the
// node count, which meant the animation could only fade nodes in. There was no
// notion of "this transfer is happening right now", so nothing could draw a
// transfer travelling from one wallet to another — the graph faded in once over
// ~17s (a flat rate regardless of size) and was then completely inert. Any
// attempt to add per-edge motion with its own setTimeout/rAF loops would have
// produced several independent clocks that drift apart from each other and from
// the scrubber.
//
// So: ONE timeline, built from the real data, and every visual state (which
// nodes exist yet, which edges are drawn, which transfer is in flight and how
// far along it is) is a pure function of one clock value. Play/pause/scrub/
// replay all just move that clock.
//
// The ordering is real, not decorative. Every step is an actual transaction
// from the trace, ordered causally (money cannot leave an address the trail
// has not reached yet) with real on-chain time — `firstTaintedAt`, persisted
// by the engine per node — breaking ties. See the ordering loop below for why
// pure timestamp order was tried first and had to be abandoned.
// ============================================================
import { useMemo } from "react";
import type { TraceNode, TraceEdge } from "@/lib/mock-data";

export interface TimelineStep {
  /** The transfer being made in this step. */
  edgeId: string;
  fromId: string;
  toId: string;
  /** Real on-chain time this transfer landed; null when the engine had none. */
  at: string | null;
  amount: string;
}

export interface TimelineFrame {
  /** Nodes that exist at this point in the replay. */
  revealedNodes: Set<string>;
  /** Edges fully drawn at this point. */
  revealedEdges: Set<string>;
  /** The transfer currently in flight, if any, and how far along it is (0-1). */
  active: { step: TimelineStep; t: number } | null;
  /** Index of the current step and the total, for "transfer 4 / 37" readouts. */
  stepIndex: number;
  stepCount: number;
  /** Nodes that have just received funds, for the arrival pulse. */
  arriving: Set<string>;
}

export interface TraceTimeline {
  steps: TimelineStep[];
  rootIds: string[];
  frameAt: (progress: number) => TimelineFrame;
}

export function useTraceTimeline(
  nodes: TraceNode[],
  edges: TraceEdge[],
): TraceTimeline {
  return useMemo(() => {
    const nodeIds = new Set(nodes.map((n) => n.id));
    const hasParent = new Set(
      edges.filter((e) => nodeIds.has(e.from) && nodeIds.has(e.to)).map((e) => e.to),
    );
    // Roots are present from t=0 — they are what the investigator searched for,
    // not something the money "arrived at".
    const rootIds = nodes.filter((n) => !hasParent.has(n.id)).map((n) => n.id);

    const timeOf = new Map(nodes.map((n) => [n.id, n.firstTaintedAt ?? null]));

    const candidates: TimelineStep[] = edges
      .filter((e) => nodeIds.has(e.from) && nodeIds.has(e.to))
      .map((e) => ({
        edgeId: e.id,
        fromId: e.from,
        toId: e.to,
        at: e.timestamp || timeOf.get(e.to) || null,
        amount: e.amount,
      }));

    const timeValue = (step: TimelineStep): number =>
      // Transfers with no recorded timestamp sort last rather than being
      // silently treated as "the beginning of time".
      step.at ? new Date(step.at).getTime() : Number.POSITIVE_INFINITY;

    // Order the replay CAUSALLY, breaking ties by real on-chain time.
    //
    // Sorting purely by timestamp looked right in theory and was wrong on
    // screen: on-chain time does not line up with hop depth, so a hop-5
    // transfer that happened earlier than a hop-2 transfer was replayed first,
    // and the trail appeared as disconnected islands materialising out of
    // order. Funds cannot leave an address the trail has not reached yet, so
    // the replay must respect that: at each step, consider only the transfers
    // whose SOURCE has already been reached, and among those play the one that
    // genuinely happened first.
    //
    // This stays faithful to the data — every step is a real transaction and
    // the ordering within what is reachable is real chronology — while the
    // picture builds outward from the reported wallet the way the money did.
    const steps: TimelineStep[] = [];
    const reached = new Set<string>(rootIds);
    const remaining = [...candidates];
    while (remaining.length > 0) {
      let bestIdx = -1;
      let bestTime = Number.POSITIVE_INFINITY;
      for (let i = 0; i < remaining.length; i++) {
        const cand = remaining[i]!;
        if (!reached.has(cand.fromId)) continue;
        const t = timeValue(cand);
        if (bestIdx === -1 || t < bestTime) {
          bestIdx = i;
          bestTime = t;
        }
      }
      if (bestIdx === -1) {
        // Nothing left is reachable — the remainder is genuinely disconnected
        // from the root (e.g. an edge whose parent was pruned by the node
        // budget). Append it in chronological order rather than dropping it:
        // hiding real edges to keep the picture tidy is the one thing the
        // renderer must never do.
        remaining.sort((a, b) => timeValue(a) - timeValue(b));
        for (const rest of remaining) {
          steps.push(rest);
          reached.add(rest.fromId);
          reached.add(rest.toId);
        }
        break;
      }
      const [chosen] = remaining.splice(bestIdx, 1);
      steps.push(chosen!);
      reached.add(chosen!.toId);
    }

    const frameAt = (progress: number): TimelineFrame => {
      const revealedNodes = new Set<string>(rootIds);
      const revealedEdges = new Set<string>();
      const arriving = new Set<string>();

      if (steps.length === 0) {
        // A single-node trace (or one with no usable edges) is fully revealed:
        // there is no motion to show, and hiding the one node it did find would
        // misrepresent an honest result as an empty one.
        nodes.forEach((n) => revealedNodes.add(n.id));
        return {
          revealedNodes,
          revealedEdges,
          active: null,
          stepIndex: 0,
          stepCount: 0,
          arriving,
        };
      }

      const clamped = Math.max(0, Math.min(1, progress));
      const exact = clamped * steps.length;
      const completed = Math.floor(exact);
      const frac = exact - completed;

      for (let i = 0; i < Math.min(completed, steps.length); i++) {
        const s = steps[i]!;
        revealedEdges.add(s.edgeId);
        revealedNodes.add(s.fromId);
        revealedNodes.add(s.toId);
        // The most recent couple of arrivals still glow, so the eye can follow
        // where the money just went.
        if (i >= completed - 2) arriving.add(s.toId);
      }

      let active: TimelineFrame["active"] = null;
      if (completed < steps.length) {
        const s = steps[completed]!;
        // The source must exist for a transfer to leave it.
        revealedNodes.add(s.fromId);
        active = { step: s, t: frac };
        // The destination materialises as the transfer lands, not before.
        if (frac > 0.72) revealedNodes.add(s.toId);
      }

      return {
        revealedNodes,
        revealedEdges,
        active,
        stepIndex: Math.min(completed, steps.length),
        stepCount: steps.length,
        arriving,
      };
    };

    return { steps, rootIds, frameAt };
  }, [nodes, edges]);
}
