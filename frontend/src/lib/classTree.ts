// Package tree for the class filter panel: package → sub-packages + one bucket
// per class kind. Pure, so `classTree.check.ts` can run it under plain Node.

import type { ClassGraphNode } from "./api";

export interface KindBucket<T = ClassGraphNode> {
  kind: string;
  nodes: T[];
  ids: string[];
}

export interface PkgNode<T = ClassGraphNode> {
  path: string;
  label: string;
  children: PkgNode<T>[];
  buckets: KindBucket<T>[];
  /** Every class id in this package and its sub-packages. */
  ids: string[];
}

type Leaf = { id: string; name: string; kind: string; package: string };

/** Group `nodes` by their dotted `package` into a tree. `kindOrder` sets the
 *  bucket order; kinds outside it sort last. The root carries the classes that
 *  have no package (external placeholders). */
export function buildClassTree<T extends Leaf>(
  nodes: T[],
  kindOrder: readonly string[],
): PkgNode<T> {
  type Raw = { path: string; kids: Map<string, Raw>; classes: T[] };
  const root: Raw = { path: "", kids: new Map(), classes: [] };
  for (const n of nodes) {
    let at = root;
    for (const seg of n.package ? n.package.split(".") : []) {
      const path = at.path ? `${at.path}.${seg}` : seg;
      if (!at.kids.has(seg)) at.kids.set(seg, { path, kids: new Map(), classes: [] });
      at = at.kids.get(seg)!;
    }
    at.classes.push(n);
  }
  const rank = (k: string) => (kindOrder.includes(k) ? kindOrder.indexOf(k) : kindOrder.length);
  const finish = (r: Raw, label: string): PkgNode<T> => {
    // A package that only holds one sub-package reads better folded into it
    // (`com.acme.orders` instead of three nested rows).
    if (r !== root && r.classes.length === 0 && r.kids.size === 1) {
      const [[seg, only]] = [...r.kids];
      return finish(only, `${label}.${seg}`);
    }
    const children = [...r.kids.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([seg, k]) => finish(k, seg));
    const byKind = new Map<string, T[]>();
    for (const c of r.classes) {
      if (!byKind.has(c.kind)) byKind.set(c.kind, []);
      byKind.get(c.kind)!.push(c);
    }
    const buckets = [...byKind.entries()]
      .sort(([a], [b]) => rank(a) - rank(b))
      .map(([kind, ns]) => {
        ns.sort((a, b) => a.name.localeCompare(b.name));
        return { kind, nodes: ns, ids: ns.map((n) => n.id) };
      });
    return {
      path: r.path,
      label,
      children,
      buckets,
      ids: [...buckets.flatMap((b) => b.ids), ...children.flatMap((c) => c.ids)],
    };
  };
  return finish(root, "");
}
