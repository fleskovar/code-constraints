// Self-check for revealRing. Run: node src/lib/reveal.check.ts
import assert from "node:assert/strict";
import { revealRing } from "./reveal.ts";

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
  ref("Base", "World"),
  ref("Tests", "Base"),
];
const ring = (visible: string[], dir: "up" | "down", via: "all" | "inheritance" | "association") =>
  revealRing(new Set(visible), edges, dir, via);

// Down on a base class reveals every class derived from it, not only the first.
assert.deepEqual(ring(["Base"], "down", "inheritance"), ["Platform", "Gate", "Lava"]);
// Up reveals the base types.
assert.deepEqual(ring(["Base"], "up", "inheritance"), ["IThing"]);
// A second step goes one ring further and skips what is visible already.
assert.deepEqual(ring(["Base", "Platform", "Gate", "Lava"], "down", "inheritance"), ["FastGate"]);

// References keep their stored direction: down is the referenced type.
assert.deepEqual(ring(["Base"], "down", "association"), ["World"]);
assert.deepEqual(ring(["Base"], "up", "association"), ["Tests"]);

// "all" follows both kinds.
assert.deepEqual(new Set(ring(["Base"], "down", "all")), new Set(["Platform", "Gate", "Lava", "World"]));
assert.deepEqual(new Set(ring(["Base"], "up", "all")), new Set(["IThing", "Tests"]));

// Package edges carry no kind: every `via` follows them, in the stored direction.
const pkg = [{ source: "app", target: "core" }];
assert.deepEqual(revealRing(new Set(["app"]), pkg, "down", "inheritance"), ["core"]);
assert.deepEqual(revealRing(new Set(["core"]), pkg, "up", "association"), ["app"]);

console.log("reveal: ok");
