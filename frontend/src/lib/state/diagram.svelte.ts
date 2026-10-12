// Shared, top-level Svelte 5 runes state for the diagram explorer.
//
// A single $state proxy object is read and written by both the SvelteFlow
// canvas and the side panel, giving bidirectional selection sync without an
// event bus.

import type { ClassGraphEdge } from "../api";
import { revealRing } from "../reveal";

/** A directed graph edge — only source/target are required for graph traversal. */
export interface GraphEdge {
  source: string;
  target: string;
  /** Class edges carry their kind so reveal can follow one kind only. */
  kind?: "inheritance" | "association";
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
  /** Bump to request the canvas fit the viewport on `selectedClassId`. */
  fitToken: number;
  /** A short message at the bottom of the canvas. Empty: none. See `notify`. */
  notice: string;
  /** Model-orientation edges of the active diagram (source→target as stored in
   *  `graph.edges`, NOT the render-swapped inheritance edges). Published by the
   *  active *DiagramFlow so the top toolbar can drive graph navigation. */
  currentEdges: GraphEdge[];
  /** Rings of node ids added by progressive reveal, newest last, so Collapse
   *  and the per-direction hide buttons can undo one ring at a time. */
  revealStack: RevealRing[];
  /** Which class edges progressive reveal follows. */
  revealVia: RevealVia;
  /** Level-of-detail rendering: progressively simplify the canvas as you zoom
   *  out. Toggleable; `lodTier` is derived from the live zoom by the canvas. */
  lodEnabled: boolean;
  lodTier: LodTier;
  /** Member compartments drawn on class nodes (the "Display" menu). */
  showAttributes: boolean;
  showOperations: boolean;
  /** Relationship lines drawn on the class canvas, per edge kind. */
  showInheritanceEdges: boolean;
  showReferenceEdges: boolean;
  /** Whether the kind-colour legend overlay is expanded. */
  legendOpen: boolean;
  /** Qualified class names a deep link (?focus=A,B) or a pushed proposal asked
   *  us to pre-filter to. Consumed (and cleared) by the class canvas once the
   *  graph is loaded and qnames can be resolved to node ids. */
  pendingFocusQnames: string[] | null;
}

/** Zoom-driven detail tiers. `full` = everything; `mid` = header-only nodes,
 *  edges still drawn; `far` = header-only nodes, plus, while no visibility
 *  filter is set, edges hidden and derived classes hidden (overview of
 *  base/standalone types only). */
export type LodTier = "full" | "mid" | "far";

export type RevealDirection = "up" | "down";
export type RevealVia = "all" | "inheritance" | "association";

/** One step of progressive reveal: the ids it added and which way it went. */
export interface RevealRing {
  direction: RevealDirection;
  ids: string[];
}

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
  fitToken: 0,
  notice: "",
  currentEdges: [] as GraphEdge[],
  revealStack: [] as RevealRing[],
  revealVia: "all" as RevealVia,
  lodEnabled: true,
  lodTier: "full" as LodTier,
  showAttributes: true,
  showOperations: true,
  showInheritanceEdges: true,
  showReferenceEdges: true,
  legendOpen: true,
  pendingFocusQnames: null as string[] | null,
});

// ---------- mutators (free functions; all of them mutate the singleton) ----------

/** Ask the class canvas to pre-filter to these qualified names once loaded. */
let noticeTimer: ReturnType<typeof setTimeout> | undefined;

/** Show a short message at the bottom of the canvas for `ms` milliseconds. */
export function notify(message: string, ms = 2200): void {
  diagramState.notice = message;
  clearTimeout(noticeTimer);
  noticeTimer = setTimeout(() => (diagramState.notice = ""), ms);
}

export function setPendingFocus(qnames: string[] | null): void {
  diagramState.pendingFocusQnames =
    qnames && qnames.length > 0 ? qnames : null;
}

/** Select one node. `fit` also centres the canvas on it: the default, for a
 *  selection made away from the canvas (a list, the inspector, a walkthrough).
 *  A click on the canvas passes `false`, the node is on screen already. */
export function setSelected(id: string | null, fit = true): void {
  diagramState.selectedClassId = id;
  // Selecting (or deselecting) a node clears any edge selection.
  diagramState.selectedEdgeId = null;
  diagramState.highlightedNodeIds = new Set();
  if (id && fit) diagramState.fitToken += 1;
}

/** Select several nodes at once (the `a` key). They render highlighted. */
export function selectMany(ids: Iterable<string>): void {
  diagramState.selectedEdgeId = null;
  diagramState.highlightedNodeIds = new Set(ids);
}

/** Replace the selection with `ids`. The first one is the primary node: the
 *  inspector shows it and the Tab key cycles from it. */
export function selectSet(ids: string[]): void {
  setSelected(ids[0] ?? null, false);
  if (ids.length > 1) selectMany(ids);
}

/** Add a node to the selection, or take it out (Shift+click). The node that
 *  was added last is the primary one. */
export function toggleSelected(id: string): void {
  // A selected edge highlights its two ends. They are not a node selection.
  const ids = new Set(diagramState.selectedEdgeId ? [] : selectedIds());
  if (ids.has(id)) ids.delete(id);
  else ids.add(id);
  diagramState.selectedEdgeId = null;
  diagramState.selectedClassId = ids.has(id) ? id : ([...ids].at(-1) ?? null);
  diagramState.highlightedNodeIds = ids;
}

const VIA_CYCLE: RevealVia[] = ["inheritance", "association", "all"];

/** Switch "follow" to the next kind (a double tap on Tab) and return it. */
export function cycleRevealVia(): RevealVia {
  const next = VIA_CYCLE[(VIA_CYCLE.indexOf(diagramState.revealVia) + 1) % VIA_CYCLE.length];
  diagramState.revealVia = next;
  return next;
}

/** Hide `ids` and clear the selection (the `h` key). `allIds` is every node id
 *  of the diagram, for the case that no visibility filter is set. */
export function hideMany(ids: Iterable<string>, allIds: Iterable<string>): void {
  const next = new Set(diagramState.visibleClassIds ?? allIds);
  for (const id of ids) next.delete(id);
  diagramState.visibleClassIds = next;
  setSelected(null);
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

/** The selected node plus the nodes `a` (or a selected edge) highlighted. */
export function selectedIds(): string[] {
  const ids = new Set(diagramState.highlightedNodeIds);
  if (diagramState.selectedClassId) ids.add(diagramState.selectedClassId);
  return [...ids];
}

/** Grow the visible set by one directed ring around the selection (see
 *  `revealRing` for what each direction follows). Newly-added ids are pushed
 *  onto `revealStack` so Collapse can remove them, and the canvas re-runs its
 *  layout. No-op while everything is shown (`visibleClassIds === null`).
 *  Returns the ids it revealed. */
export function reveal(direction: RevealDirection, edges: GraphEdge[]): string[] {
  const cur = diagramState.visibleClassIds;
  if (cur === null) return [];
  const added = revealRing(cur, selectedIds(), edges, direction, diagramState.revealVia);
  if (added.length === 0) return [];
  diagramState.revealStack = [...diagramState.revealStack, { direction, ids: added }];
  diagramState.visibleClassIds = new Set([...cur, ...added]);
  // A revealed node still holds its position from the full-graph layout, which
  // can be tens of thousands of pixels from its neighbour. Lay out the visible
  // subgraph again so the new ring lands next to the nodes that revealed it.
  requestRelayout();
  return added;
}

/** Undo the most recent reveal ring, or the most recent ring of `direction`
 *  when one is given (so "hide upstream" works after a later downstream step).
 *  Only removes ids that no other ring still on the stack also added. */
export function collapseReveal(direction?: RevealDirection): void {
  const stack = diagramState.revealStack;
  let at = stack.length - 1;
  while (at >= 0 && direction && stack[at].direction !== direction) at--;
  if (at < 0) return;
  const remaining = stack.filter((_, i) => i !== at);
  const kept = new Set(remaining.flatMap((r) => r.ids));
  const cur = diagramState.visibleClassIds;
  if (cur !== null) {
    const next = new Set(cur);
    for (const id of stack[at].ids) if (!kept.has(id)) next.delete(id);
    diagramState.visibleClassIds = next;
  }
  diagramState.revealStack = remaining;
}

/** Whether a ring of `direction` (or any ring) can be hidden. */
export function canCollapse(direction?: RevealDirection): boolean {
  return diagramState.revealStack.some((r) => !direction || r.direction === direction);
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
