# `forbidden-package-references` — catalog is a leaf package (Julia)

## What this proves

A package edge is **derived** by aggregating class references to their containing packages, and the rule fires once per forbidden `(from, to)` pair — never on the reverse edge, never on an intra-package edge, and never on a `to:` package that nothing actually points at.

**Engine:** A — drift — `cdec check`  
**Constraint:** [`forbidden-package-references`](../../../../../docs/RULES_CATALOGUE.md#forbidden-package-references)  
**Language:** Julia  
**Runner:** `tests/case_runner.py::_run_check`

## Inputs

| File | What it is |
| --- | --- |
| `inputs/case.yaml` | Engine and language — the ambient inputs, written down so nothing about the run is implicit |
| `inputs/rules.yaml` | One rule entry: `from:` the leaf package, `to:` the packages it must never depend on |
| `inputs/src/catalog/Catalog.jl` | the violating struct — a cross-module field type |
| `inputs/src/orders/Orders.jl` | the allowed direction |
| `inputs/src/users/Users.jl` | a forbidden target nothing points at |

### Why each element is there

| Element | Demonstrates |
| --- | --- |
| `catalog.Catalog.Book` | field `reserved::Order`. **The violation.** |
| `catalog.Catalog.Author` | field `work::Book`: a self-edge, dropped by clause 3 |
| `orders.Orders.Order` | field `item::Book`: the permitted direction |
| `users.Users.Customer` | in `to:`, but no `catalog` struct references it |

Every element has a line. An element nobody can justify is an element to delete.

## Expected output

`outputs/violations.json` — One row per violation, sorted by `(rule, element, member)`. `element` is the qualified name the violation is attributed to; `member` is the discriminating signature the review key is derived from.

```json
[
  {
    "element": "catalog.Catalog",
    "member": "->orders.Orders",
    "rule": "catalog-is-a-leaf-package",
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
4. The rule fires for each derived edge whose source matches `from:` **and** whose target matches `to:`. It is directional — the reverse edge is never examined.
5. The violation is attributed to the **source package**, with the discriminator `->{target}`, so two forbidden targets from one package are two violations.

### Applying them

**Step 1 — the class reference graph, then aggregate to packages (clauses 1–3):**

| Class edge | Package edge | Kept? |
| --- | --- | --- |
| `catalog.Catalog.Book -> orders.Orders.Order` | `catalog.Catalog -> orders.Orders` | ✅ |
| `catalog.Catalog.Author -> catalog.Catalog.Book` | `catalog.Catalog -> catalog.Catalog` | ❌ clause 3 |
| `orders.Orders.Order -> catalog.Catalog.Book` | `orders.Orders -> catalog.Catalog` | ✅ (but not in `from:`) |

**Step 2 — apply `from: [catalog]`, `to: [orders, users]` (clause 4):**

| Package edge | Matches `from:`? | Matches `to:`? | Fires? |
| --- | --- | --- | --- |
| `catalog -> orders` | ✅ | ✅ | **yes** |
| the reverse edge | ❌ — not in `from:` | — | no |

`users` is named in `to:` but has no incoming edge from `catalog`, so it is never
reached. Listing a package as forbidden is not enough; an edge must exist.

**Step 3 — the finding (clause 5):** attributed to the source *package*, not to the
offending class, because the edge may come from any class in it.

### Elements that produce nothing

| Element | Why it is absent from the output |
| --- | --- |
| `users.Users.Customer` | No `catalog` struct references it. |
| `catalog.Catalog.Author` | Its only edge is intra-package. |

### Julia-specific notes

Julia packages **nest**: the directory `catalog/` and the `module Catalog` inside it produce `catalog` containing `catalog.Catalog`, and the classes live in the inner one. That is why `rules.yaml` uses `catalog.**` rather than `catalog` — a bare `catalog` would match the outer package, which holds no classes and therefore has no edges.

## Why this proves the code is correct

- **It pins:** that package edges are *derived* rather than read from imports, that intra-package edges are dropped, that the rule is directional, and that the violation is attributed to the source package with a `->target` discriminator.
- **It would catch:** a regression that made the rule symmetric, one that stopped unwrapping collections, one that started firing on self-edges, or one that attributed the violation to the offending class instead of its package.
- **It does not cover:** the `ignore:` option, several forbidden targets from one source, and `scope: diff` — those live in `tests/test_lint_engine.py`, which drives the rule off synthetic `Project` models rather than real source.

## How to run and debug

```bash
make test-case CASE=check/forbidden-package-references/julia
make debug-case CASE=check/forbidden-package-references/julia
```

**Start here:** breakpoint in `tests/case_runner.py::_run_check`, then step into the engine. Inspect `ctx.outgoing_pkg_refs` — that dict is the derived package graph the walkthrough builds by hand.

## When to change this case

A red run is a regression until proven otherwise — do not regenerate the baseline to get green. If the requirement genuinely changed, add a new case for the new behaviour and retire this one explicitly. Regenerating (`UPDATE_BASELINES=1 make test-case CASE=check/forbidden-package-references/julia`) produces a diff a human reads line by line, in a commit that changes baselines and nothing else.
