# `no-cyclic-package-dependencies` — two packages name each other (C#)

## What this proves

Every elementary cycle in the derived package graph is reported **once**, canonicalised so the alphabetically-first package leads — so the finding is stable however the graph is walked. Packages that are merely *in* the graph, or that sit downstream of a cycle, do not appear.

**Engine:** A — drift — `cdec check`  
**Constraint:** [`no-cyclic-package-dependencies`](../../../../../docs/RULES_CATALOGUE.md#no-cyclic-package-dependencies)  
**Language:** C#  
**Runner:** `tests/case_runner.py::_run_check`

## Inputs

| File | What it is |
| --- | --- |
| `inputs/case.yaml` | Engine and language — the ambient inputs, written down so nothing about the run is implicit |
| `inputs/rules.yaml` | The rule entry. This rule takes no options — it is either on or off |
| `inputs/src/Catalog/Book.cs` | source under test |
| `inputs/src/Orders/Order.cs` | source under test |
| `inputs/src/Users/Customer.cs` | source under test |

### Why each element is there

| Element | Demonstrates |
| --- | --- |
| `Users.Customer` | a field typed `Order` → the `Users -> Orders` edge |
| `Orders.Order` | fields typed `Customer` and `Book` → `Orders -> Users` (closing the cycle) and `Orders -> Catalog` (acyclic) |
| `Catalog.Book` | a leaf: referenced by orders, references nobody. It cannot be in a cycle |

Every element has a line. An element nobody can justify is an element to delete.

## Expected output

`outputs/violations.json` — One row per violation, sorted by `(rule, element, member)`. `element` is the qualified name the violation is attributed to; `member` is the discriminating signature the review key is derived from.

```json
[
  {
    "element": "Orders",
    "member": "Orders -> Users -> Orders",
    "rule": "no-cyclic-package-dependencies",
    "severity": "error"
  }
]
```

**Deliberately absent:** messages, file paths and line numbers. A rule's `message:` is prose that gets rewritten, a path is a Windows/POSIX hazard, and a line number moves when someone adds a comment. What the baseline pins is the *identity* of each finding.

## Baseline provenance

**Computed by hand** from the constraint's definition in the catalogue, then checked against the engine. The walkthrough below is the derivation: every row in the baseline appears in it, and no row appears that the walkthrough does not produce.

## Walkthrough

### The rules, stated once

1. A class **A references B** when an attribute type, an operation parameter or return type, a body-level dependency recorded by the parser, or a base class of A resolves to B. Collection wrappers are unwrapped, so `list[B]` / `List<B>` / `B[]` all resolve to `B`.
2. Package edges are **derived**, not read from imports: for every class edge `A -> B`, add `package(A) -> package(B)`.
3. **Self-edges are dropped.** `package(A) == package(B)` never produces an edge (`lint/engine.py::_build_context`).
4. Every **elementary cycle** in the derived package graph is reported once.
5. The cycle is **canonicalised** by rotating it so the alphabetically-first package leads, so `[A,B]` and `[B,A]` collapse to one report.
6. The violation is attributed to that leading package, with the full chain (`a -> b -> a`) as the discriminator.

### Applying them

**Step 1 — derive the package graph (clauses 1–3):**

| Class edge | Package edge |
| --- | --- |
| `Users.Customer -> Orders.Order` | `Users -> Orders` |
| `Orders.Order -> Users.Customer` | `Orders -> Users` |
| `Orders.Order -> Catalog.Book` | `Orders -> Catalog` |

Graph: `{ Orders: {Users, Catalog}, Users: {Orders} }`. `Catalog` has no outgoing edges.

**Step 2 — enumerate elementary cycles (clause 4):**

There is exactly one: `Orders -> Users -> Orders`. The walk finds it from both `Orders` and `Users`,
which is why clause 5 exists.

**Step 3 — canonicalise (clause 5):**

The cycle's node set is `{Orders, Users}`. Alphabetically `Orders` < `Users`, so the chain is
rotated to lead with `Orders`. The discovery starting at `Users` normalises to the same tuple
and is discarded — **one cycle, one finding**.

**Step 4 — the finding (clause 6):** attributed to `Orders`, with the full chain
`Orders -> Users -> Orders` as the discriminator, so the message can name the whole loop.

### Elements that produce nothing

| Element | Why it is absent from the output |
| --- | --- |
| `Catalog.Book` | `Catalog` is downstream of the cycle but not in it — it has no outgoing edges at all, so no cycle can pass through it. |

## Why this proves the code is correct

- **It pins:** that cycles are found in the *derived* package graph, that each cycle is reported exactly once however it is discovered, and that the canonical rotation puts the alphabetically-first package first.
- **It would catch:** a regression that reported one cycle once per member package, one that lost the canonical rotation so the attributed package varied with walk order, or one that started reporting acyclic leaves.
- **It does not cover:** three-or-more-package cycles, nested cycles sharing an edge, and the `ignore:` option; see `tests/test_lint_engine.py`.

## How to run and debug

```bash
make test-case CASE=check/no-cyclic-package-dependencies/csharp
make debug-case CASE=check/no-cyclic-package-dependencies/csharp
```

**Start here:** breakpoint in `tests/case_runner.py::_run_check`, then step into the engine. Step into `_find_cycles` with `ctx.outgoing_pkg_refs` as its input.

## When to change this case

A red run is a regression until proven otherwise — do not regenerate the baseline to get green. If the requirement genuinely changed, add a new case for the new behaviour and retire this one explicitly. Regenerating (`UPDATE_BASELINES=1 make test-case CASE=check/no-cyclic-package-dependencies/csharp`) produces a diff a human reads line by line, in a commit that changes baselines and nothing else.
