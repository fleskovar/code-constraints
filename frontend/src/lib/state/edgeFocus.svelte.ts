// Shared UI state for the "edge focus" popup. With an edge selected in the
// class diagram, pressing `f` (or the toolbar button) opens a small SvelteFlow
// canvas showing just the two classes joined by that edge, side by side.
//
// The trigger (toolbar button) and the keydown handler live in different
// components, but only ClassDiagramFlow holds the loaded ClassGraph. So the
// flow publishes its graph here via `setEdgeFocusGraph`, and `openEdgeFocus`
// resolves the currently-selected edge id against it. Mutators are free
// functions so they survive HMR (same pattern as `diagram.svelte.ts`).

import type { ClassGraph, ClassGraphEdge, ClassGraphNode } from "../api";

interface EdgeFocusState {
  open: boolean;
  edge: ClassGraphEdge | null;
  /** Model source endpoint (graph orientation, pre render-swap). */
  source: ClassGraphNode | null;
  /** Model target endpoint. */
  target: ClassGraphNode | null;
}

export const edgeFocus = $state<EdgeFocusState>({
  open: false,
  edge: null,
  source: null,
  target: null,
});

// Published by ClassDiagramFlow when its graph loads; null when the view
// resets/switches so a stale graph can't be focused.
let currentGraph: ClassGraph | null = null;

export function setEdgeFocusGraph(g: ClassGraph | null): void {
  currentGraph = g;
}

/** Resolve `edgeId` against the published graph and open the popup. No-op if
 *  the edge or either endpoint can't be found. */
export function openEdgeFocus(edgeId: string): void {
  if (!currentGraph) return;
  const edge = currentGraph.edges.find((e) => e.id === edgeId);
  if (!edge) return;
  const source = currentGraph.nodes.find((n) => n.id === edge.source);
  const target = currentGraph.nodes.find((n) => n.id === edge.target);
  if (!source || !target) return;
  edgeFocus.edge = edge;
  edgeFocus.source = source;
  edgeFocus.target = target;
  edgeFocus.open = true;
}

export function closeEdgeFocus(): void {
  edgeFocus.open = false;
  edgeFocus.edge = null;
  edgeFocus.source = null;
  edgeFocus.target = null;
}
