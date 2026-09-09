# `max-class-fanout` — the hub class (C#)

## What this proves

Fanout counts **distinct** referenced project classes, compares strictly greater than `limit`, and honours `ignore:` for the class whose whole job is wiring. The under-limit row names one collaborator twice on purpose, so a regression that counted references rather than distinct targets would change its answer.

**Engine:** A — drift — `cdec check`  
**Constraint:** [`max-class-fanout`](../../../../../docs/RULES_CATALOGUE.md#max-class-fanout)  
**Language:** C#  
**Runner:** `tests/case_runner.py::_run_check`

## Inputs

| File | What it is |
| --- | --- |
| `inputs/case.yaml` | Engine and language — the ambient inputs, written down so nothing about the run is implicit |
| `inputs/rules.yaml` | One rule entry: `limit: 6` and an `ignore:` for the composition root |
| `inputs/src/App/Root.cs` | also over the limit, but ignored |
| `inputs/src/Orders/Checkout.cs` | the hub — eight distinct references |
| `inputs/src/Orders/Collaborators.cs` | eight leaf classes with no outgoing references |
| `inputs/src/Orders/Pricing.cs` | four distinct references, one named twice |

### Why each element is there

| Element | Demonstrates |
| --- | --- |
| `Orders.CheckoutService` | eight distinct property/parameter types. **The violation.** |
| `Orders.PriceCalculator` | four distinct types, with `Cart` twice |
| `App.CompositionRoot` | also eight, but named in `ignore:` |
| `Orders.Cart and seven siblings` | leaf collaborators, fanout 0 |

Every element has a line. An element nobody can justify is an element to delete.

## Expected output

`outputs/violations.json` — One row per violation, sorted by `(rule, element, member)`. `element` is the qualified name the violation is attributed to; `member` is the discriminating signature the review key is derived from.

```json
[
  {
    "element": "Orders.CheckoutService",
    "rule": "bounded-class-fanout",
    "severity": "warning"
  }
]
```

**Deliberately absent:** messages, file paths and line numbers. A rule's `message:` is prose that gets rewritten, a path is a Windows/POSIX hazard, and a line number moves when someone adds a comment. What the baseline pins is the *identity* of each finding.

## Baseline provenance

**Computed by hand** from the constraint's definition in the catalogue, then checked against the engine. The walkthrough below is the derivation: every row in the baseline appears in it, and no row appears that the walkthrough does not produce.

## Walkthrough

### The rules, stated once

1. A class **A references B** when an attribute type, an operation parameter or return type, a body-level dependency recorded by the parser, or a base class of A resolves to B. Collection wrappers are unwrapped, so `list[B]` / `List<B>` / `B[]` all resolve to `B`.
2. Fanout is the number of **distinct** project classes a class references. Naming the same collaborator twice counts once.
3. The rule fires when `fanout > limit`. At exactly `limit` it is silent.
4. `ignore:` exempts a class — the right home for a deliberate composition root or facade whose whole job is wiring.
5. Only project classes count; `str`, `int`, `decimal` and friends are not in the class index and never resolve.

### Applying them

**Step 1 — count distinct outgoing references (clauses 1–2).**

| Class | Referenced classes | Distinct count |
| --- | --- | --- |
| `Orders.CheckoutService` | Cart, ReceiptFactory, PaymentGateway, AuditLog, Notifier, Inventory, PriceTable, ShippingCalculator | **8** |
| `Orders.PriceCalculator` | Cart *(named twice)*, PriceTable, Inventory, ShippingCalculator | **4** |
| `App.CompositionRoot` | the same eight as the hub | **8** |
| each collaborator | — | **0** |

`Orders.PriceCalculator` names `Cart` in two different parameters. Clause 2 says that counts **once**,
so its fanout is 4 and not 5 — this row exists purely to pin that.

**Step 2 — compare against `limit: 6` (clause 3).**

| Class | Fanout | `fanout > 6`? |
| --- | --- | --- |
| `Orders.CheckoutService` | 8 | ✅ |
| `App.CompositionRoot` | 8 | ✅ |
| `Orders.PriceCalculator` | 4 | ❌ |

**Step 3 — apply `ignore:` (clause 4).** `App.CompositionRoot` is over the limit and is exempted by
name: wiring everything together is a composition root's entire purpose, and a rule that
cannot say so is a rule teams switch off.

**Step 4 — the finding.** One class, at `severity: warning` — high fanout is an
early-warning metric, not a law.

### Elements that produce nothing

| Element | Why it is absent from the output |
| --- | --- |
| `Orders.PriceCalculator` | Fanout 4, under the limit of 6. Note it would be 5 if the rule counted references rather than distinct targets. |
| `App.CompositionRoot` | Fanout 8, over the limit, but named in `ignore:`. |
| `the eight collaborators` | Fanout 0 — they reference nothing. `max-class-fanout` looks *outward* only, which is exactly the opposite of `dangling-classes`. |

## Why this proves the code is correct

- **It pins:** that the count is of *distinct* targets, that the comparison is strictly greater-than, and that `ignore:` exempts the deliberate hub.
- **It would catch:** a regression that counted references rather than distinct targets (the four-reference class here would jump to five), one that flipped `>` to `>=`, or one that counted built-in types.
- **It does not cover:** the default limit of 10, a non-integer `limit` (a hard config error), and `scope: diff`; see `tests/test_lint_engine.py`.

## How to run and debug

```bash
make test-case CASE=check/max-class-fanout/csharp
make debug-case CASE=check/max-class-fanout/csharp
```

**Start here:** breakpoint in `tests/case_runner.py::_run_check`, then step into the engine. Inspect `ctx.outgoing_refs[qn]` — a set, which is where "distinct" comes from.

## When to change this case

A red run is a regression until proven otherwise — do not regenerate the baseline to get green. If the requirement genuinely changed, add a new case for the new behaviour and retire this one explicitly. Regenerating (`UPDATE_BASELINES=1 make test-case CASE=check/max-class-fanout/csharp`) produces a diff a human reads line by line, in a commit that changes baselines and nothing else.
