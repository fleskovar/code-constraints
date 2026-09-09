// Run dagre over a SvelteFlow node/edge set and return positions.
//
// Pure function — no Svelte / React dependency. The class canvas calls this
// once on first load to seed positions; further drags are tracked by
// SvelteFlow's own state.

import Dagre from "@dagrejs/dagre";

export interface LayoutNode {
  id: string;
  width: number;
  height: number;
}

export interface LayoutEdge {
  source: string;
  target: string;
  // Higher-weight edges are kept shorter and straighter by dagre's ranker, so
  // weighting inheritance above association makes the generalization hierarchy
  // drive the vertical layout. Both default to 1 (dagre's own defaults).
  weight?: number;
  minlen?: number;
}

export interface LayoutOptions {
  direction?: "TB" | "BT" | "LR" | "RL";
  nodeSep?: number;
  rankSep?: number;
}

export function layoutNodes(
  nodes: LayoutNode[],
  edges: LayoutEdge[],
  opts: LayoutOptions = {},
): Map<string, { x: number; y: number }> {
  const g = new Dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({
    rankdir: opts.direction ?? "BT",
    nodesep: opts.nodeSep ?? 60,
    ranksep: opts.rankSep ?? 100,
  });

  for (const n of nodes) {
    g.setNode(n.id, { width: n.width, height: n.height });
  }
  for (const e of edges) {
    g.setEdge(e.source, e.target, {
      weight: e.weight ?? 1,
      minlen: e.minlen ?? 1,
    });
  }

  Dagre.layout(g);

  const positions = new Map<string, { x: number; y: number }>();
  for (const n of nodes) {
    const laid = g.node(n.id);
    if (laid) {
      // dagre returns the centre — SvelteFlow expects the top-left.
      positions.set(n.id, {
        x: laid.x - n.width / 2,
        y: laid.y - n.height / 2,
      });
    }
  }
  return positions;
}
