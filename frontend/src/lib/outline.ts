// The canvas selection as a Markdown list, for a document (Ctrl+C).
// Pure, so it runs under plain node. Self-check: node src/lib/outline.check.ts
import type { GraphEdge } from "./state/diagram.svelte";

const INDENT = "    ";

/** One bullet per id, in the given order. */
export function flatOutline(ids: string[], label: (id: string) => string): string {
  return ids.map((id) => `- ${label(id)}`).join("\n");
}

/** A nested Markdown list of `ids` that follows the inheritance lines between
 *  them: a class is one level below each of its base types.
 *
 *  - Only a line between two of the given ids counts, the way the canvas draws
 *    it. A class whose base is not in `ids` starts at the top level.
 *  - A class with several bases in `ids` is listed below each of them, so
 *    every inheritance line of the selection is in the text.
 *  - `ids` gives the order of the top level and of the children of one base.
 *    The caller passes the canvas order (left to right). */
export function inheritanceOutline(
  ids: string[],
  edges: GraphEdge[],
  label: (id: string) => string,
): string {
  const chosen = new Set(ids);
  const rank = new Map(ids.map((id, i) => [id, i]));
  const children = new Map<string, string[]>();
  const derived = new Set<string>();
  for (const e of edges) {
    // An inheritance edge is stored child → parent.
    if (e.kind !== "inheritance" || e.source === e.target) continue;
    if (!chosen.has(e.source) || !chosen.has(e.target)) continue;
    if (!children.has(e.target)) children.set(e.target, []);
    children.get(e.target)!.push(e.source);
    derived.add(e.source);
  }
  const roots = ids.filter((id) => !derived.has(id));
  // No top level: the edges form a loop, which real code cannot have.
  if (roots.length === 0) return flatOutline(ids, label);

  const lines: string[] = [];
  const walk = (id: string, depth: number, path: Set<string>) => {
    lines.push(`${INDENT.repeat(depth)}- ${label(id)}`);
    const below = [...(children.get(id) ?? [])].sort((a, b) => rank.get(a)! - rank.get(b)!);
    // `path` stops a loop between classes that are not at the top level.
    for (const c of below) if (!path.has(c)) walk(c, depth + 1, new Set(path).add(c));
  };
  for (const r of roots) walk(r, 0, new Set([r]));
  return lines.join("\n");
}
