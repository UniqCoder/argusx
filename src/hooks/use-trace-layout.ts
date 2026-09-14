// ============================================================
// useTraceLayout — computes real node positions for the trace graph.
//
// TraceGraph (investigation.tsx) reads node.x/node.y directly and does no
// layout itself, so this hook is the only thing standing between "flat list of
// hops" and "a graph that reflects which wallets connect to which".
//
// Why this is a HOP-LAYERED layout and not a plain force blob:
//
//   1. Direction. A money trail's whole point is "value moved from here to
//      there". A symmetric force layout places hop 5 wherever it happens to
//      settle — sometimes left of the root — so the single most important fact
//      in the picture is lost. Layering by real hop distance makes the x axis
//      mean something: left is the reported wallet, right is where the money
//      went.
//
//   2. It has to survive real trace sizes. The previous version ran d3-force
//      into a FIXED 980x420 viewBox and then clamped every node into it. That
//      was measured, not guessed: at 40 nodes, 40% of nodes were pinned onto
//      the padding border with 20 overlapping pairs and centres as close as
//      14.7px (labels need >=68px). At 80 nodes it was 70% clamped, 140
//      overlapping pairs, centres 0.1px apart — i.e. a solid clump. Traces now
//      routinely return 50-75 nodes, so clamping was destroying the graph.
//      This version sizes the canvas to the content instead, and the renderer
//      pans/zooms over it.
//
// Vertical placement inside a layer is force-relaxed so siblings don't collide
// and so a child sits near its parent, which keeps edges short and readable.
// ============================================================
import { useMemo } from "react";
import type { TraceNode, TraceEdge } from "@/lib/mock-data";

// Horizontal distance between hop layers, and vertical distance between
// siblings. NODE_FOOTPRINT is the real visual footprint: TraceGraph draws
// THREE label lines below every node now (entity label, plain-English type,
// truncated address), reaching to about r+44 below centre — collision
// resolution used to only account for an r=18 circle with one label line
// (~34px), so siblings could end up as close as 68px apart while needing
// close to 190px to keep three-line labels from overlapping the next
// node's circle. That's what made a busy hop read as a solid, illegible
// clump instead of separated wallets.
const LAYER_GAP = 230;
const ROW_GAP = 110;
const NODE_FOOTPRINT = 95;
const MARGIN = 70;

export interface TraceLayout {
  nodes: TraceNode[];
  /** Content size, so the renderer can fit/pan/zoom instead of clipping. */
  width: number;
  height: number;
}

export function useTraceLayout(
  nodes: TraceNode[],
  edges: TraceEdge[],
): TraceLayout {
  return useMemo(() => {
    if (nodes.length === 0) {
      return { nodes, width: 980, height: 420 };
    }
    if (nodes.length === 1) {
      const only = nodes[0];
      return {
        nodes: only ? [{ ...only, x: 490, y: 210 }] : nodes,
        width: 980,
        height: 420,
      };
    }

    // ── 1. Assign each node a layer ────────────────────────────────────────
    // Prefer the engine's real hop number. Fall back to BFS distance over the
    // edges for any node without one, so a node never silently lands in
    // layer 0 next to the root it isn't adjacent to.
    const byId = new Map(nodes.map((n) => [n.id, n]));
    const children = new Map<string, string[]>();
    const parentOf = new Map<string, string>();
    for (const e of edges) {
      if (!byId.has(e.from) || !byId.has(e.to)) continue;
      if (!children.has(e.from)) children.set(e.from, []);
      children.get(e.from)!.push(e.to);
      if (!parentOf.has(e.to)) parentOf.set(e.to, e.from);
    }

    const layerOf = new Map<string, number>();
    for (const n of nodes) {
      // Negative hops are allowed on purpose: a real victim/complaint node
      // (from cross-victim correlation) is injected at hop -1 so it draws
      // one layer BEFORE the searched wallet, not clamped on top of it.
      if (typeof n.hop === "number" && Number.isFinite(n.hop)) {
        layerOf.set(n.id, n.hop);
      }
    }
    if (layerOf.size < nodes.length) {
      const roots = nodes.filter((n) => !parentOf.has(n.id)).map((n) => n.id);
      const queue = roots.length ? [...roots] : [nodes[0]!.id];
      for (const r of queue) if (!layerOf.has(r)) layerOf.set(r, 0);
      let head = 0;
      while (head < queue.length) {
        const id = queue[head++]!;
        const depth = layerOf.get(id) ?? 0;
        for (const c of children.get(id) ?? []) {
          if (!layerOf.has(c)) {
            layerOf.set(c, depth + 1);
            queue.push(c);
          }
        }
      }
      // Anything still unplaced is genuinely disconnected — park it in its own
      // trailing layer rather than pretending it is adjacent to the root.
      const maxLayer = Math.max(0, ...[...layerOf.values()]);
      for (const n of nodes) if (!layerOf.has(n.id)) layerOf.set(n.id, maxLayer + 1);
    }

    // ── 2. Group by layer, ordered so siblings stay together ───────────────
    const layers = new Map<number, string[]>();
    for (const n of nodes) {
      const l = layerOf.get(n.id) ?? 0;
      if (!layers.has(l)) layers.set(l, []);
      layers.get(l)!.push(n.id);
    }
    const layerKeys = [...layers.keys()].sort((a, b) => a - b);
    // Order each layer by its parent's position in the previous layer, so
    // edges don't criss-cross more than they have to.
    const orderIndex = new Map<string, number>();
    for (const l of layerKeys) {
      const ids = layers.get(l)!;
      ids.sort((a, b) => {
        const pa = orderIndex.get(parentOf.get(a) ?? "") ?? 0;
        const pb = orderIndex.get(parentOf.get(b) ?? "") ?? 0;
        if (pa !== pb) return pa - pb;
        return a.localeCompare(b);
      });
      ids.forEach((id, i) => orderIndex.set(id, i));
    }

    // ── 3. Position ────────────────────────────────────────────────────────
    const widest = Math.max(...layerKeys.map((l) => layers.get(l)!.length));
    const contentHeight = Math.max(420, widest * ROW_GAP + MARGIN * 2);
    const contentWidth = Math.max(
      980,
      (layerKeys.length - 1) * LAYER_GAP + MARGIN * 2,
    );

    // Position by INDEX within layerKeys, not the raw layer number — layer
    // numbers can be negative (a victim node at hop -1) or have gaps, and
    // either would otherwise throw off the x axis or collide with MARGIN.
    const layerIndexOf = new Map(layerKeys.map((l, i) => [l, i]));
    const pos = new Map<string, { x: number; y: number }>();
    for (const l of layerKeys) {
      const ids = layers.get(l)!;
      const x = MARGIN + (layerIndexOf.get(l) ?? 0) * LAYER_GAP;
      // Centre the layer vertically, then nudge each node toward its parent.
      const span = (ids.length - 1) * ROW_GAP;
      let y = contentHeight / 2 - span / 2;
      for (const id of ids) {
        pos.set(id, { x, y });
        y += ROW_GAP;
      }
    }

    // Pull each node toward its parent's y, then push apart any siblings that
    // ended up closer than a label's worth of space. A few relaxation passes
    // are enough and, unlike a full simulation, cost nothing at these sizes.
    for (let pass = 0; pass < 30; pass++) {
      for (const l of layerKeys) {
        const ids = layers.get(l)!;
        for (const id of ids) {
          const p = parentOf.get(id);
          if (!p) continue;
          const pp = pos.get(p);
          const me = pos.get(id);
          if (!pp || !me) continue;
          me.y += (pp.y - me.y) * 0.18;
        }
        // Resolve collisions within the layer.
        const sorted = [...ids].sort((a, b) => pos.get(a)!.y - pos.get(b)!.y);
        for (let i = 1; i < sorted.length; i++) {
          const prev = pos.get(sorted[i - 1]!)!;
          const cur = pos.get(sorted[i]!)!;
          const need = NODE_FOOTPRINT * 2;
          if (cur.y - prev.y < need) {
            const shift = (need - (cur.y - prev.y)) / 2;
            prev.y -= shift;
            cur.y += shift;
          }
        }
      }
    }

    // ── 4. Normalise into the content box ──────────────────────────────────
    const ys = [...pos.values()].map((p) => p.y);
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);
    const offsetY = MARGIN - minY;
    const height = Math.max(420, maxY - minY + MARGIN * 2);

    const laidOut = nodes.map((n) => {
      const p = pos.get(n.id);
      return p ? { ...n, x: p.x, y: p.y + offsetY } : n;
    });

    return { nodes: laidOut, width: contentWidth, height };
  }, [nodes, edges]);
}
