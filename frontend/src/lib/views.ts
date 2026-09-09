// Saved "views" of the class diagram. A view captures the visible-class set,
// node positions, and current selection. Views are exported to a local file
// the user can move wherever they like, then imported back later.

import {
  diagramState,
  setSelected,
  showAll as svcShowAll,
  setVisibleSet,
} from "./state/diagram.svelte";
import type { ClassGraph, ServerView } from "./api";

export const VIEW_SCHEMA = "code-constraints/view@1";

export interface SavedView {
  schema: typeof VIEW_SCHEMA;
  name: string;
  xmiId?: string;
  /** `null` is the sentinel meaning "everything visible". */
  visibleClassIds: string[] | null;
  nodePositions: Record<string, { x: number; y: number }>;
  selectedClassId: string | null;
  savedAt: string;
}

export function snapshotView(name: string, xmiId?: string): SavedView {
  return {
    schema: VIEW_SCHEMA,
    name,
    xmiId,
    visibleClassIds:
      diagramState.visibleClassIds === null
        ? null
        : [...diagramState.visibleClassIds],
    nodePositions: Object.fromEntries(diagramState.nodePositions),
    selectedClassId: diagramState.selectedClassId,
    savedAt: new Date().toISOString(),
  };
}

export function exportViewToFile(name: string, xmiId?: string): void {
  const view = snapshotView(name, xmiId);
  const blob = new Blob([JSON.stringify(view, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${sanitizeFilename(name)}.cdecview.json`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  // Revoke after the browser has had a chance to start the download.
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function importViewFromFile(file: File): Promise<SavedView> {
  const text = await file.text();
  const parsed = JSON.parse(text) as Partial<SavedView>;
  if (parsed.schema !== VIEW_SCHEMA) {
    throw new Error(
      `Unrecognised view schema: ${parsed.schema ?? "(missing)"}. Expected ${VIEW_SCHEMA}.`,
    );
  }
  return parsed as SavedView;
}

/**
 * Apply a SavedView to the live diagramState. Optionally constrain to the set
 * of class ids known to the current diagram — unknown ids in the saved view
 * are silently dropped so positional drift doesn't ghost-render missing nodes.
 */
export function applyView(view: SavedView, knownIds?: Set<string>): void {
  if (view.visibleClassIds === null) {
    svcShowAll();
  } else {
    const ids = knownIds
      ? view.visibleClassIds.filter((id) => knownIds.has(id))
      : view.visibleClassIds;
    setVisibleSet(ids);
  }

  const positions = new Map<string, { x: number; y: number }>();
  for (const [id, p] of Object.entries(view.nodePositions ?? {})) {
    if (knownIds && !knownIds.has(id)) continue;
    if (typeof p?.x === "number" && typeof p?.y === "number") {
      positions.set(id, { x: p.x, y: p.y });
    }
  }
  diagramState.nodePositions = positions;

  if (
    view.selectedClassId &&
    (!knownIds || knownIds.has(view.selectedClassId))
  ) {
    setSelected(view.selectedClassId);
  } else {
    setSelected(null);
  }
}

function sanitizeFilename(name: string): string {
  const trimmed = name.trim() || "view";
  return trimmed.replace(/[^a-zA-Z0-9_.-]+/g, "_").slice(0, 60);
}

// ---------- server-side views (code-constraints/view@2, qualified names) ----------

/** Convert a human view name to a safe lowercase filename stem (without extension).
 *  Must produce output that satisfies the backend's _SAFE_VIEW_RE pattern. */
export function nameToFilename(name: string): string {
  const stem = (name.trim() || "view")
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 58);
  return (stem || "view") + ".json";
}

/** Snapshot the current diagram state as a server view, translating internal
 *  SHA1 IDs to qualified class names using the provided graph. */
export function snapshotServerView(name: string, graph: ClassGraph): ServerView {
  const idToQname = new Map(graph.nodes.map((n) => [n.id, n.qualifiedName]));

  let visible: string[];
  if (diagramState.visibleClassIds === null) {
    // "show all" — store all qualified names explicitly (v2 has no null sentinel)
    visible = graph.nodes.map((n) => n.qualifiedName);
  } else {
    visible = [];
    for (const id of diagramState.visibleClassIds) {
      const qn = idToQname.get(id);
      if (qn !== undefined) visible.push(qn);
    }
  }

  const positions: Record<string, { x: number; y: number }> = {};
  for (const [id, pos] of diagramState.nodePositions) {
    const qn = idToQname.get(id);
    if (qn !== undefined) positions[qn] = pos;
  }

  return {
    schema: "code-constraints/view@2",
    name,
    visible,
    ...(Object.keys(positions).length > 0 ? { positions } : {}),
  };
}

/** Apply a server view to the live diagram state. Qualified names that no longer
 *  exist in the current graph are dropped and returned in `dropped`. */
export function applyServerView(
  view: ServerView,
  graph: ClassGraph,
): { dropped: string[] } {
  const qnameToId = new Map(graph.nodes.map((n) => [n.qualifiedName, n.id]));

  const dropped: string[] = [];
  const ids: string[] = [];
  for (const qn of view.visible) {
    const id = qnameToId.get(qn);
    if (id !== undefined) {
      ids.push(id);
    } else {
      dropped.push(qn);
    }
  }

  setVisibleSet(ids);

  const positions = new Map<string, { x: number; y: number }>();
  for (const [qn, pos] of Object.entries(view.positions ?? {})) {
    const id = qnameToId.get(qn);
    if (id !== undefined && typeof pos?.x === "number" && typeof pos?.y === "number") {
      positions.set(id, { x: pos.x, y: pos.y });
    }
  }
  diagramState.nodePositions = positions;

  setSelected(null);

  return { dropped };
}
