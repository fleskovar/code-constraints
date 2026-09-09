# `dangling-classes` — dead code versus entry points (TypeScript)

## What this proves

`dangling-classes` looks at **incoming** references only, and needs two escape hatches to be usable: `entry_points:` for classes application bootstrap wires up, and `framework_bases:` for classes a framework instantiates. This case exercises one genuinely dead class against both hatches.

**Engine:** A — drift — `cdec check`  
**Constraint:** [`dangling-classes`](../../../../../docs/RULES_CATALOGUE.md#dangling-classes)  
**Language:** TypeScript  
**Runner:** `tests/case_runner.py::_run_check`

## Inputs

| File | What it is |
| --- | --- |
| `inputs/case.yaml` | Engine and language — the ambient inputs, written down so nothing about the run is implicit |
| `inputs/rules.yaml` | One rule entry with the `entry_points:` allow-list and the `framework_bases:` override |
| `inputs/src/orders/cart.ts` | a class with an incoming reference |
| `inputs/src/orders/checkout.ts` | an entry point |
| `inputs/src/orders/legacyPricing.ts` | the dead class |
| `inputs/src/web/controller.ts` | a framework-derived class |

### Why each element is there

| Element | Demonstrates |
| --- | --- |
| `orders.Cart` | referenced by `CheckoutService` — has an incoming edge |
| `orders.CheckoutService` | **no** incoming references, but named in `entry_points:` |
| `orders.LegacyPriceTable` | no incoming references and no hatch. **The violation.** |
| `web.OrderController` | `extends BaseCommand`, the configured framework base |

Every element has a line. An element nobody can justify is an element to delete.

## Expected output

`outputs/violations.json` — One row per violation, sorted by `(rule, element, member)`. `element` is the qualified name the violation is attributed to; `member` is the discriminating signature the review key is derived from.

```json
[
  {
    "element": "orders.LegacyPriceTable",
    "rule": "no-dangling-classes",
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
2. The check is on **incoming** references only. A class that references plenty of others but is referenced by nobody is exactly what this finds.
3. **Self-references do not count** as incoming.
4. A class matching `entry_points:` is exempt. The glob is matched against **both** the qualified name and the bare class name.
5. A class deriving — transitively, through project ancestors — from any name in `framework_bases:` is exempt. Setting the option **replaces** the built-in list (`MonoBehaviour`, `ScriptableObject`, …).

### Applying them

**Step 1 — invert the reference graph (clauses 1–3).** For each class, who points at it?

| Class | Incoming references | Verdict |
| --- | --- | --- |
| `orders.Cart` | `{orders.CheckoutService}` | referenced → silent |
| `orders.CheckoutService` | `{}` (empty) | exempt: `entry_points:` |
| `orders.LegacyPriceTable` | `{}` (empty) | **dangling → fires** |
| `web.OrderController` | `{}` (empty) | exempt: `framework_bases: [BaseCommand]` |

**Step 2 — apply the escape hatches (clauses 4–5).** Note the order: a class is only
tested for incoming references *after* the hatches have had their say, so an entry point
with no references is silent rather than "reported and then suppressed".

**Step 3 — the finding.** One class survives both hatches with an empty incoming set.
It is reported at `severity: warning`, because dead-code detection is a *signal*: the
rule cannot tell dead code from a class the framework reaches in a way the model cannot
see. That is exactly why the two hatches exist.

### Elements that produce nothing

| Element | Why it is absent from the output |
| --- | --- |
| `orders.Cart` | Referenced by `CheckoutService`. |
| `orders.CheckoutService` | Listed in `entry_points:`. |
| `web.OrderController` | `BaseCommand` is never imported or defined — the rule matches bases textually, so an unresolvable base name still works as a framework hatch. |

## Why this proves the code is correct

- **It pins:** that the direction is incoming-only, that `entry_points:` and `framework_bases:` are the two escape hatches, and that a class with outgoing references but no incoming ones is still dangling.
- **It would catch:** a regression that counted outgoing references as reachability, one that let self-references keep a class alive, or one that stopped honouring a configured framework base.
- **It does not cover:** transitive framework inheritance through several project ancestors, the bare-name form of `entry_points:`, and `scope: diff`; see `tests/test_lint_engine.py`.

## How to run and debug

```bash
make test-case CASE=check/dangling-classes/typescript
make debug-case CASE=check/dangling-classes/typescript
```

**Start here:** breakpoint in `tests/case_runner.py::_run_check`, then step into the engine. Inspect `ctx.incoming_refs` — the inverted reference graph.

## When to change this case

A red run is a regression until proven otherwise — do not regenerate the baseline to get green. If the requirement genuinely changed, add a new case for the new behaviour and retire this one explicitly. Regenerating (`UPDATE_BASELINES=1 make test-case CASE=check/dangling-classes/typescript`) produces a diff a human reads line by line, in a commit that changes baselines and nothing else.
