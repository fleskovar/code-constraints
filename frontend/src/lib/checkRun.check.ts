// Self-check for lib/checkRun.ts. Run: node src/lib/checkRun.check.ts
import assert from "node:assert/strict";
import type { CheckResult, CheckViolation } from "./api.ts";
import { changeSince, classOf, filterRows, groupRows, issueRows } from "./checkRun.ts";

const v = (key: string, rule_id: string, qn: string, severity: "error" | "warning" = "error", file = ""): CheckViolation => ({
  key,
  rule_id,
  engine: "check",
  severity,
  qualified_name: qn,
  message: `message of ${key}`,
  waivable: true,
  ...(file ? { location: { file, start_line: 1, end_line: 1 } } : {}),
});

const run = (open: CheckViolation[], accepted: CheckViolation[] = [], bypassed: CheckViolation[] = []): CheckResult =>
  ({ report: { violations: open, suppressed: accepted, bypassed } }) as unknown as CheckResult;

const a = v("V-A", "fanout", "shop.Order", "error", "shop/order.py");
const b = v("V-B", "fanout", "shop.Invoice", "warning", "shop/invoice.py");
const c = v("V-C", "layers", "shop.Order.total", "error", "shop/order.py");
const old = v("V-OLD", "layers", "shop.Cart");

// The first run has nothing to compare with: no row is new.
assert.deepEqual(issueRows(run([a, b]), null).map((r) => r.isNew), [false, false]);

// Open first, then bypassed, then accepted. Only an open row can be new.
const before = run([a, old]);
const now = run([a, c], [b]);
const rows = issueRows(now, before);
assert.deepEqual(rows.map((r) => [r.violation.key, r.state, r.isNew]), [
  ["V-A", "open", false],
  ["V-C", "open", true],
  ["V-B", "accepted", false],
]);

// An accepted issue is fixed for the gate: it was open, and it is not open now.
const delta = changeSince(run([a, b, old]), now);
assert.deepEqual(delta.fixed.map((x) => x.key), ["V-B", "V-OLD"]);
assert.deepEqual(delta.added.map((x) => x.key), ["V-C"]);

// Filters: state, severity, and text over key, rule, element, message and file.
const all = { query: "", severities: new Set(["error", "warning"]), states: new Set(["open", "accepted", "bypassed"] as const) };
assert.equal(filterRows(rows, all).length, 3);
assert.deepEqual(filterRows(rows, { ...all, states: new Set(["open"] as const) }).map((r) => r.violation.key), ["V-A", "V-C"]);
assert.deepEqual(filterRows(rows, { ...all, severities: new Set(["warning"]) }).map((r) => r.violation.key), ["V-B"]);
assert.deepEqual(filterRows(rows, { ...all, query: "INVOICE" }).map((r) => r.violation.key), ["V-B"]);
assert.deepEqual(filterRows(rows, { ...all, query: "layers" }).map((r) => r.violation.key), ["V-C"]);

// Groups keep the order of their first row.
assert.deepEqual(groupRows(rows, "rule").map(([k, g]) => [k, g.length]), [["fanout", 2], ["layers", 1]]);
assert.deepEqual(groupRows(rows, "file").map(([k]) => k), ["shop/order.py", "shop/invoice.py"]);
assert.deepEqual(groupRows([...rows, ...issueRows(run([old]), null)], "file").map(([k]) => k).at(-1), "(no file)");

// The class of an issue: exact, or the longest class prefix at a dot.
const classes = ["shop.Order", "shop.OrderLine", "shop"];
assert.equal(classOf("shop.Order", classes), "shop.Order");
assert.equal(classOf("shop.Order.total", classes), "shop.Order");
assert.equal(classOf("shop.OrderLine.qty", classes), "shop.OrderLine");
assert.equal(classOf("billing.Tax", classes), null);

console.log("checkRun: ok");
