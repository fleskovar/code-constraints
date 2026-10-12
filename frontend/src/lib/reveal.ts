// Directed steps over the diagram graph: the ring a reveal adds, the nodes the
// `w` / `s` keys move to, and the siblings the Tab key cycles through.
// Pure, so it runs under plain node. Self-check: node src/lib/reveal.check.ts
import type { GraphEdge, RevealDirection, RevealVia } from "./state/diagram.svelte";

/** node id → the ids one step away in `direction`.
 *
 *  `down` is what the canvas draws below a node: the types it references and
 *  the classes derived from it. `up` is what is above: the types that
 *  reference it and its base classes. `via` limits class edges to one kind. */
function adjacency(
  edges: GraphEdge[],
  direction: RevealDirection,
  via: RevealVia,
): Map<string, Set<string>> {
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
  return adj;
}

/** Every id one directed step away from `seeds`, in edge order, without the
 *  seeds. It does not look at what is visible. */
export function stepFrom(
  seeds: Iterable<string>,
  edges: GraphEdge[],
  direction: RevealDirection,
  via: RevealVia,
): string[] {
  const adj = adjacency(edges, direction, via);
  const from = new Set(seeds);
  const out = new Set<string>();
  for (const id of from) for (const n of adj.get(id) ?? []) if (!from.has(n)) out.add(n);
  return [...out];
}

/** The ids one step of progressive reveal adds: one directed step away from
 *  `seeds`, without the ids that are visible already. The ring grows from the
 *  seeds only (the user's selection), not from every visible node: a second
 *  step from one class must not also expand its siblings. A seed that is not
 *  visible is ignored. */
export function revealRing(
  visible: ReadonlySet<string>,
  seeds: Iterable<string>,
  edges: GraphEdge[],
  direction: RevealDirection,
  via: RevealVia,
): string[] {
  const shown = [...seeds].filter((id) => visible.has(id));
  return stepFrom(shown, edges, direction, via).filter((id) => !visible.has(id));
}

/** The visible nodes on the same level as `id`: the visible children of its
 *  visible parents, `id` included. A node with no visible parent is on the top
 *  level, with every other visible node that has no visible parent. The order
 *  is that of `visible`; the caller sorts by canvas position. */
export function siblings(
  id: string,
  visible: ReadonlySet<string>,
  edges: GraphEdge[],
  via: RevealVia,
): string[] {
  const up = adjacency(edges, "up", via);
  const down = adjacency(edges, "down", via);
  const visibleParents = (n: string) => [...(up.get(n) ?? [])].filter((p) => visible.has(p));
  const parents = visibleParents(id);
  const level = new Set<string>([id]);
  if (parents.length === 0) {
    for (const n of visible) if (visibleParents(n).length === 0) level.add(n);
  } else {
    for (const p of parents) for (const c of down.get(p) ?? []) if (visible.has(c)) level.add(c);
  }
  return [...visible].filter((n) => level.has(n));
}
