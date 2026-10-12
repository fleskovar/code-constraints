// Self-check for lib/outline.ts. Run: node src/lib/outline.check.ts
import assert from "node:assert/strict";
import { flatOutline, inheritanceOutline } from "./outline.ts";

// Stored the way the backend emits them: inheritance child→parent.
const inh = (source: string, target: string) => ({ source, target, kind: "inheritance" as const });
const ref = (source: string, target: string) => ({ source, target, kind: "association" as const });
const label = (id: string) => `namespace.${id} (${id}.py)`;
const lines = (...l: string[]) => l.join("\n");

// Two classes with no relation: two bullets, in the given order.
assert.equal(
  inheritanceOutline(["A", "B"], [], label),
  lines("- namespace.A (A.py)", "- namespace.B (B.py)"),
);

// C inherits from A, D inherits from C: each level is four spaces deeper.
const edges = [inh("C", "A"), inh("D", "C")];
assert.equal(
  inheritanceOutline(["A", "B", "C", "D"], edges, label),
  lines(
    "- namespace.A (A.py)",
    "    - namespace.C (C.py)",
    "        - namespace.D (D.py)",
    "- namespace.B (B.py)",
  ),
);
// The order of the ids is the order of the top level and of siblings.
assert.equal(
  inheritanceOutline(["B", "D", "C", "A"], edges, label),
  lines(
    "- namespace.B (B.py)",
    "- namespace.A (A.py)",
    "    - namespace.C (C.py)",
    "        - namespace.D (D.py)",
  ),
);
const id = (x: string) => x;
assert.equal(
  inheritanceOutline(["Base", "Z", "M", "K"], [inh("K", "Base"), inh("M", "Base"), inh("Z", "Base")], id),
  lines("- Base", "    - Z", "    - M", "    - K"),
);

// Only a line between two selected classes counts. With C left out, D has no
// selected base and starts at the top level.
assert.equal(inheritanceOutline(["A", "D"], edges, id), lines("- A", "- D"));

// A class with two selected bases is listed below each of them.
assert.equal(
  inheritanceOutline(["Base", "IThing", "Gate"], [inh("Gate", "Base"), inh("Gate", "IThing")], id),
  lines("- Base", "    - Gate", "- IThing", "    - Gate"),
);

// A reference is not part of the hierarchy.
assert.equal(inheritanceOutline(["A", "B"], [ref("A", "B")], id), lines("- A", "- B"));

// A loop cannot hang the copy. Real code has none; a damaged model can.
assert.equal(inheritanceOutline(["A", "B"], [inh("A", "B"), inh("B", "A")], id), lines("- A", "- B"));
assert.equal(
  inheritanceOutline(["R", "A", "B"], [inh("A", "R"), inh("B", "A"), inh("A", "B")], id),
  lines("- R", "    - A", "        - B"),
);

assert.equal(flatOutline(["A", "B"], label), lines("- namespace.A (A.py)", "- namespace.B (B.py)"));

console.log("outline: ok");
