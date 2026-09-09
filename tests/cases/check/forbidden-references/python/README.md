# `forbidden-references` — the catalogue must not know the buyer (Python)

## What this proves

`forbidden-references` is the class-level scalpel to `forbidden-package-references`' package-level wall: it matches source and target *classes* with no aggregation, and it is directional — a class that references a forbidden target but does not itself match `from:` is never examined.

**Engine:** A — drift — `cdec check`  
**Constraint:** [`forbidden-references`](../../../../../docs/RULES_CATALOGUE.md#forbidden-references)  
**Language:** Python  
**Runner:** `tests/case_runner.py::_run_check`

## Inputs

| File | What it is |
| --- | --- |
| `inputs/case.yaml` | Engine and language — the ambient inputs, written down so nothing about the run is implicit |
| `inputs/rules.yaml` | One rule entry: `from:` the source classes, `to:` the forbidden target classes |
| `inputs/src/catalog/author.py` | source under test |
| `inputs/src/catalog/book.py` | source under test |
| `inputs/src/orders/order.py` | source under test |
| `inputs/src/users/customer.py` | source under test |

### Why each element is there

| Element | Demonstrates |
| --- | --- |
| `catalog.Book` | a `Customer` parameter and attribute type → `users.Customer`. **The violation.** |
| `catalog.Author` | matches `from:` but references nothing in `to:` — silent |
| `orders.Order` | references `users.Customer` too, but is not in `from:`. The rule is directional |
| `users.Customer` | the forbidden target itself; it is never a *source* |

Every element has a line. An element nobody can justify is an element to delete.

## Expected output

`outputs/violations.json` — One row per violation, sorted by `(rule, element, member)`. `element` is the qualified name the violation is attributed to; `member` is the discriminating signature the review key is derived from.

```json
[
  {
    "element": "catalog.Book",
    "member": "->users.Customer",
    "rule": "catalog-does-not-reference-customer",
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
2. The rule fires for each class edge whose **source class** matches `from:` and whose **target class** matches `to:`. Unlike the package rule this is class-to-class, with no aggregation.
3. It is directional. A class that references a forbidden target but does not itself match `from:` is never examined.
4. The violation is attributed to the **source class**, with the discriminator `->{target}`.

### Applying them

**Step 1 — the class reference graph (clause 1):**

| Source class | Reference | Resolves to |
| --- | --- | --- |
| `catalog.Book` | a `Customer` parameter and attribute type | `users.Customer` |
| `orders.Order` | a `Customer` field | `users.Customer` |
| `catalog.Author` | — | — |

**Step 2 — apply `from: [catalog.**]`, `to: [users.Customer]` (clauses 2–3):**

| Edge | Source in `from:`? | Target in `to:`? | Fires? |
| --- | --- | --- | --- |
| `catalog.Book -> users.Customer` | ✅ | ✅ | **yes** |
| `orders.Order -> users.Customer` | ❌ | ✅ | no |

**Step 3 — the finding (clause 4):** attributed to `catalog.Book` with the discriminator
`->users.Customer`. Note the contrast with the package rule: here the *class* is named, because
the rule knows exactly which class carries the offending reference.

### Elements that produce nothing

| Element | Why it is absent from the output |
| --- | --- |
| `catalog.Author` | It matches `from:` but has no edge into `to:`. |
| `orders.Order` | It has the forbidden edge but does not match `from:`. |

## Why this proves the code is correct

- **It pins:** that the rule matches on class qualified names rather than packages, that it is directional, and that the discriminator names the target.
- **It would catch:** a regression that made the rule symmetric, one that widened `from:` to match packages, or one that dropped the `->target` discriminator so two forbidden targets from one class collapsed into one waiver.
- **It does not cover:** the `ignore:` option (which applies to both ends) and `scope: diff`; see `tests/test_lint_engine.py`.

## How to run and debug

```bash
make test-case CASE=check/forbidden-references/python
make debug-case CASE=check/forbidden-references/python
```

**Start here:** breakpoint in `tests/case_runner.py::_run_check`, then step into the engine. Inspect `ctx.outgoing_refs` — the class-level graph.

## When to change this case

A red run is a regression until proven otherwise — do not regenerate the baseline to get green. If the requirement genuinely changed, add a new case for the new behaviour and retire this one explicitly. Regenerating (`UPDATE_BASELINES=1 make test-case CASE=check/forbidden-references/python`) produces a diff a human reads line by line, in a commit that changes baselines and nothing else.
