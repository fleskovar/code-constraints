// The ring of ids that one step of progressive reveal adds to the canvas.
// Pure, so it runs under plain node. Self-check: node src/lib/reveal.check.ts
import type { GraphEdge, RevealDirection, RevealVia } from "./state/diagram.svelte";

/** Ids one directed step away from `visible`, in edge order, without the ids
 *  that are visible already. `down` reveals what the canvas draws below a
 *  node: the types it references and the classes derived from it. `up` reveals
 *  what is above: the types that reference it and its base classes. `via`
 *  limits class edges to one kind. */
export function revealRing(
  visible: ReadonlySet<string>,
  edges: GraphEdge[],
  direction: RevealDirection,
  via: RevealVia,
): string[] {
  const adj = new Map<string, Set<string>>();
  for (const e of edges) {
    // Edges without a kind (package dependencies) are always followed.
    if (via !== "all" && e.kind && e.kind !== via) continue;
    // An inheritance edge is stored child→parent, but the base is drawn on top.
    // Follow it backwards, or `down` on a base class reveals its own parents
    // and never the classes derived from it.
    const forward = (direction === "down") !== (e.kind === "inheritance");
    const from = forward ? e.source : e.target;
    const to = forward ? e.target : e.source;
    if (!adj.has(from)) adj.set(from, new Set());
    adj.get(from)!.add(to);
  }
  const added = new Set<string>();
  for (const id of visible) {
    for (const n of adj.get(id) ?? []) if (!visible.has(n)) added.add(n);
  }
  return [...added];
}
