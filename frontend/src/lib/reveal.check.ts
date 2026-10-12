// Self-check for lib/reveal.ts. Run: node src/lib/reveal.check.ts
import assert from "node:assert/strict";
import { revealRing, siblings, stepFrom } from "./reveal.ts";

// Stored the way the backend emits them: inheritance child→parent, association
// holder→referenced type.
const inh = (source: string, target: string) => ({ source, target, kind: "inheritance" as const });
const ref = (source: string, target: string) => ({ source, target, kind: "association" as const });
const edges = [
  inh("Base", "IThing"),
  inh("Platform", "Base"),
  inh("Gate", "Base"),
  inh("Lava", "Base"),
  inh("FastGate", "Gate"),
  inh("HotLava", "Lava"),
  ref("Base", "World"),
  ref("Tests", "Base"),
];
// Every visible node is a seed, unless the test names the seeds.
const ring = (
  visible: string[],
  dir: "up" | "down",
  via: "all" | "inheritance" | "association",
  seeds: string[] = visible,
) => revealRing(new Set(visible), seeds, edges, dir, via);

// Down on a base class reveals every class derived from it, not only the first.
assert.deepEqual(ring(["Base"], "down", "inheritance"), ["Platform", "Gate", "Lava"]);
// Up reveals the base types.
assert.deepEqual(ring(["Base"], "up", "inheritance"), ["IThing"]);
// A second step goes one ring further and skips what is visible already.
assert.deepEqual(ring(["Base", "Platform", "Gate", "Lava"], "down", "inheritance"), ["FastGate", "HotLava"]);

// The ring grows from the selection only. Gate and Lava are both visible and
// both have a subclass; a step from Gate must not reveal the subclass of Lava.
const family = ["Base", "Platform", "Gate", "Lava"];
assert.deepEqual(ring(family, "down", "inheritance", ["Gate"]), ["FastGate"]);
assert.deepEqual(ring(family, "down", "inheritance", ["Lava"]), ["HotLava"]);
assert.deepEqual(ring(family, "down", "inheritance", ["Gate", "Lava"]), ["FastGate", "HotLava"]);
// A selected node that is hidden reveals nothing.
assert.deepEqual(ring(["Base"], "down", "inheritance", ["Gate"]), []);

// References keep their stored direction: down is the referenced type.
assert.deepEqual(ring(["Base"], "down", "association"), ["World"]);
assert.deepEqual(ring(["Base"], "up", "association"), ["Tests"]);

// "all" follows both kinds.
assert.deepEqual(new Set(ring(["Base"], "down", "all")), new Set(["Platform", "Gate", "Lava", "World"]));
assert.deepEqual(new Set(ring(["Base"], "up", "all")), new Set(["IThing", "Tests"]));

// Package edges carry no kind: every `via` follows them, in the stored direction.
const pkg = [{ source: "app", target: "core" }];
assert.deepEqual(revealRing(new Set(["app"]), ["app"], pkg, "down", "inheritance"), ["core"]);
assert.deepEqual(revealRing(new Set(["core"]), ["core"], pkg, "up", "association"), ["app"]);

// ---------- stepFrom: where the `w` / `s` keys move to ----------

// Every neighbour, visible or not, without the seeds.
assert.deepEqual(stepFrom(["Gate", "Lava"], edges, "down", "inheritance"), ["FastGate", "HotLava"]);
assert.deepEqual(new Set(stepFrom(["Base"], edges, "up", "all")), new Set(["IThing", "Tests"]));
assert.deepEqual(stepFrom(["Base", "Gate"], edges, "down", "inheritance"), ["Platform", "Lava", "FastGate"]);
assert.deepEqual(stepFrom(["FastGate"], edges, "down", "inheritance"), []);

// ---------- siblings: what the Tab key cycles through ----------

const everything = new Set(["IThing", "Base", "Platform", "Gate", "Lava", "FastGate", "HotLava", "World", "Tests", "Solo"]);
// The children of the same parent, the node included, in the order of `visible`.
assert.deepEqual(siblings("Gate", everything, edges, "inheritance"), ["Platform", "Gate", "Lava"]);
// A cousin is not a sibling: FastGate and HotLava have different parents.
assert.deepEqual(siblings("FastGate", everything, edges, "inheritance"), ["FastGate"]);
// A hidden sibling is not in the cycle.
assert.deepEqual(siblings("Gate", new Set(["Base", "Gate", "Lava"]), edges, "inheritance"), ["Gate", "Lava"]);
// No visible parent: the top level is every visible node with no visible parent.
assert.deepEqual(siblings("Platform", new Set(["Platform", "Gate", "FastGate", "Solo"]), edges, "inheritance"), ["Platform", "Gate", "Solo"]);
// The level follows the kind of edge in use.
assert.deepEqual(siblings("World", everything, edges, "association"), ["World"]);
assert.deepEqual(new Set(siblings("World", everything, edges, "all")), new Set(["Platform", "Gate", "Lava", "World"]));

console.log("reveal: ok");
