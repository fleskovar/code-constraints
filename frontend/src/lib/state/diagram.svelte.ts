// Shared, top-level Svelte 5 runes state for the diagram explorer.
//
// A single $state proxy object is read and written by both the SvelteFlow
// canvas and the side panel, giving bidirectional selection sync without an
// event bus.

import type { ClassGraphEdge } from "../api";

/** A directed graph edge — only source/target are required for graph traversal. */
export interface GraphEdge {
  source: string;
  target: string;
}

export interface DiagramState {
  selectedClassId: string | null;
  /** The edge the user clicked, if any. Highlights the edge + its endpoints. */
  selectedEdgeId: string | null;
  /** Endpoints of the selected edge, highlighted alongside it. */
  highlightedNodeIds: Set<string>;
  // `null` means "everything visible"; once filtered, a Set of visible ids.
  visibleClassIds: Set<string> | null;
  nodePositions: Map<string, { x: number; y: number }>;
  /** Bump to request the canvas re-run its auto-layout over visible nodes. */
  relayoutToken: number;
  /** Model-orientation edges of the active diagram (source→target as stored in
   *  `graph.edges`, NOT the render-swapped inheritance edges). Published by the
   *  active *DiagramFlow so the top toolbar can drive graph navigation. */
  currentEdges: GraphEdge[];
  /** Batches of node ids added by progressive reveal, newest last, so Collapse
   *  can undo one ring at a time. */
  revealStack: string[][];
  /** Level-of-detail rendering: progressively simplify the canvas as you zoom
   *  out. Toggleable; `lodTier` is derived from the live zoom by the canvas. */
  lodEnabled: boolean;
  lodTier: LodTier;
  /** Whether the kind-colour legend overlay is expanded. */
  legendOpen: boolean;
  /** Qualified class names a deep link (?focus=A,B) or a pushed proposal asked
   *  us to pre-filter to. Consumed (and cleared) by the class canvas once the
   *  graph is loaded and qnames can be resolved to node ids. */
  pendingFocusQnames: string[] | null;
}

/** Zoom-driven detail tiers. `full` = everything; `mid` = header-only nodes,
 *  edges still drawn; `far` = header-only nodes, edges hidden, derived classes
 *  hidden (overview of base/standalone types only). */
export type LodTier = "full" | "mid" | "far";

const LOD_MID_BELOW = 0.55;
const LOD_FAR_BELOW = 0.3;

/** Map a raw zoom level to a detail tier. */
export function tierForZoom(zoom: number): LodTier {
  if (zoom >= LOD_MID_BELOW) return "full";
  if (zoom >= LOD_FAR_BELOW) return "mid";
  return "far";
}

export const diagramState: DiagramState = $state({
  selectedClassId: null as string | null,
  selectedEdgeId: null as string | null,
  highlightedNodeIds: new Set<string>(),
  visibleClassIds: null as Set<string> | null,
  nodePositions: new Map<string, { x: number; y: number }>(),
  relayoutToken: 0,
  currentEdges: [] as GraphEdge[],
  revealStack: [] as string[][],
  lodEnabled: true,
  lodTier: "full" as LodTier,
  legendOpen: true,
  pendingFocusQnames: null as string[] | null,
});

// ---------- mutators (free functions; all of them mutate the singleton) ----------

/** Ask the class canvas to pre-filter to these qualified names once loaded. */
export function setPendingFocus(qnames: string[] | null): void {
  diagramState.pendingFocusQnames =
    qnames && qnames.length > 0 ? qnames : null;
}

export function setSelected(id: string | null): void {
  diagramState.selectedClassId = id;
  // Selecting (or deselecting) a node clears any edge selection.
  diagramState.selectedEdgeId = null;
  diagramState.highlightedNodeIds = new Set();
}

/** Highlight an edge and its two endpoint nodes; clears node selection. */
export function selectEdge(
  edgeId: string,
  source: string,
  target: string,
): void {
  diagramState.selectedClassId = null;
  diagramState.selectedEdgeId = edgeId;
  diagramState.highlightedNodeIds = new Set([source, target]);
}

export function clearEdgeSelection(): void {
  diagramState.selectedEdgeId = null;
  diagramState.highlightedNodeIds = new Set();
}

export function isVisible(id: string): boolean {
  return (
    diagramState.visibleClassIds === null ||
    diagramState.visibleClassIds.has(id)
  );
}

export function setVisibleSet(ids: Iterable<string>): void {
  diagramState.visibleClassIds = new Set(ids);
}

export function showAll(): void {
  diagramState.visibleClassIds = null;
}

export function hideAll(): void {
  diagramState.visibleClassIds = new Set();
}

export function setVisible(id: string, on: boolean): void {
  const cur = diagramState.visibleClassIds;
  if (cur === null) {
    if (on) return;
    diagramState.visibleClassIds = new Set();
    return;
  }
  const next = new Set(cur);
  if (on) next.add(id);
  else next.delete(id);
  diagramState.visibleClassIds = next;
}

/** Visibility = root + everything reachable in ≤ `hops` undirected edge steps.
 *  Still used by the activity/sequence panels, which keep their own command
 *  bars (the class/package toolbar uses the directed `reveal` flow instead). */
export function isolate(
  rootId: string,
  hops: number,
  edges: GraphEdge[],
): void {
  const adj = new Map<string, Set<string>>();
  for (const e of edges) {
    if (!adj.has(e.source)) adj.set(e.source, new Set());
    if (!adj.has(e.target)) adj.set(e.target, new Set());
    adj.get(e.source)!.add(e.target);
    adj.get(e.target)!.add(e.source);
  }
  const visible = new Set<string>([rootId]);
  let frontier = new Set<string>([rootId]);
  for (let i = 0; i < hops; i++) {
    const next = new Set<string>();
    for (const id of frontier) {
      for (const n of adj.get(id) ?? []) {
        if (!visible.has(n)) {
          visible.add(n);
          next.add(n);
        }
      }
    }
    if (next.size === 0) break;
    frontier = next;
  }
  diagramState.visibleClassIds = visible;
}

/** Show only `rootId`, the seed for progressive reveal. Resets the reveal
 *  history so Collapse can't undo past the focus. */
export function focusOn(rootId: string): void {
  diagramState.visibleClassIds = new Set([rootId]);
  diagramState.revealStack = [];
}

/** Grow the visible set by one directed ring around every currently-visible
 *  node. `down` follows source→target (dependencies / parents); `up` follows
 *  target→source (dependents / children). Newly-added ids are pushed onto
 *  `revealStack` so Collapse can remove them. No-op while everything is shown
 *  (`visibleClassIds === null`). */
export function reveal(direction: "up" | "down", edges: GraphEdge[]): void {
  const cur = diagramState.visibleClassIds;
  if (cur === null) return;
  const adj = new Map<string, Set<string>>();
  for (const e of edges) {
    const from = direction === "down" ? e.source : e.target;
    const to = direction === "down" ? e.target : e.source;
    if (!adj.has(from)) adj.set(from, new Set());
    adj.get(from)!.add(to);
  }
  const added: string[] = [];
  const next = new Set(cur);
  for (const id of cur) {
    for (const n of adj.get(id) ?? []) {
      if (!next.has(n)) {
        next.add(n);
        added.push(n);
      }
    }
  }
  if (added.length === 0) return;
  diagramState.revealStack = [...diagramState.revealStack, added];
  diagramState.visibleClassIds = next;
}

/** Undo the most recent reveal ring. Only removes ids that were added by that
 *  ring and aren't claimed by an earlier ring still on the stack. */
export function collapseReveal(): void {
  const stack = diagramState.revealStack;
  if (stack.length === 0) return;
  const last = stack[stack.length - 1];
  const remaining = stack.slice(0, -1);
  const kept = new Set<string>();
  for (const batch of remaining) for (const id of batch) kept.add(id);
  const cur = diagramState.visibleClassIds;
  if (cur !== null) {
    const next = new Set(cur);
    for (const id of last) if (!kept.has(id)) next.delete(id);
    diagramState.visibleClassIds = next;
  }
  diagramState.revealStack = remaining;
}

export function setNodePosition(
  id: string,
  pos: { x: number; y: number },
): void {
  const m = new Map(diagramState.nodePositions);
  m.set(id, pos);
  diagramState.nodePositions = m;
}

export function setNodePositions(
  entries: Iterable<[string, { x: number; y: number }]>,
): void {
  const m = new Map(diagramState.nodePositions);
  for (const [id, pos] of entries) m.set(id, pos);
  diagramState.nodePositions = m;
}

/** Bump the relayout token; the canvas listens for changes and re-runs dagre. */
export function requestRelayout(): void {
  diagramState.relayoutToken += 1;
}

export function toggleLod(): void {
  diagramState.lodEnabled = !diagramState.lodEnabled;
}

/** Set the detail tier; only writes on change to avoid churn while zooming. */
export function setLodTier(tier: LodTier): void {
  if (diagramState.lodTier !== tier) diagramState.lodTier = tier;
}

export function toggleLegend(): void {
  diagramState.legendOpen = !diagramState.legendOpen;
}

/** Neighbours of `id` with edge kind + direction. */
export function relatedClasses(
  id: string,
  edges: ClassGraphEdge[],
): { id: string; kind: ClassGraphEdge["kind"]; direction: "out" | "in" }[] {
  const out: {
    id: string;
    kind: ClassGraphEdge["kind"];
    direction: "out" | "in";
  }[] = [];
  for (const e of edges) {
    if (e.source === id) out.push({ id: e.target, kind: e.kind, direction: "out" });
    else if (e.target === id)
      out.push({ id: e.source, kind: e.kind, direction: "in" });
  }
  const seen = new Set<string>();
  return out.filter((r) => (seen.has(r.id) ? false : (seen.add(r.id), true)));
}
