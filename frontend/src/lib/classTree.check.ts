// Self-check for buildClassTree. Run: node src/lib/classTree.check.ts
import assert from "node:assert/strict";
import { buildClassTree } from "./classTree.ts";

const n = (id: string, pkg: string, kind = "class") => ({ id, name: id, kind, package: pkg });

const tree = buildClassTree(
  [
    n("Order", "com.acme.orders"),
    n("IRepo", "com.acme.orders", "interface"),
    n("Money", "com.acme.orders", "struct"),
    n("Line", "com.acme.orders.lines"),
    n("Mailer", "com.acme.mail"),
    n("Base", "", "external"),
  ],
  ["class", "interface", "struct", "external"],
);

// `com` holds only `acme`, so the two fold into one row.
assert.deepEqual(tree.children.map((c) => c.label), ["com.acme"]);
const acme = tree.children[0];
assert.equal(acme.path, "com.acme");
assert.deepEqual(acme.children.map((c) => c.label), ["mail", "orders"]);

const orders = acme.children[1];
assert.deepEqual(orders.buckets.map((b) => b.kind), ["class", "interface", "struct"]);
assert.deepEqual(orders.children.map((c) => c.path), ["com.acme.orders.lines"]);
// A package's ids cover its own buckets and every sub-package.
assert.deepEqual(new Set(orders.ids), new Set(["Order", "IRepo", "Money", "Line"]));
assert.equal(acme.ids.length, 5);

// Classes with no package stay on the root.
assert.deepEqual(tree.buckets.map((b) => b.ids), [["Base"]]);

console.log("classTree: ok");
