# `@factory` — one way to build a receipt (Odin)

## What this proves

`@factory(creates=[…])` enforces "there is exactly one way to build this". Construction inside the designated factory is fine; the same call anywhere else is a violation. This case pins both, plus the delegating call that is the intended fix.

**Engine:** B — conformance — the `tag-conformance` rule  
**Constraint:** [`factory`](../../../../../docs/RULES_CATALOGUE.md#factory)  
**Language:** Odin  
**Runner:** `tests/case_runner.py::_run_enforce`

## Inputs

| File | What it is |
| --- | --- |
| `inputs/case.yaml` | Engine and language — the ambient inputs, written down so nothing about the run is implicit |
| `inputs/src/orders/receipt.odin` | source under test |

### Why each element is there

| Element | Demonstrates |
| --- | --- |
| `orders.ReceiptFactory` | carries `creates=["Receipt"]`. Its own `Receipt{total}` is permitted by clause 4 — this *is* the factory |
| `orders.CheckoutService.checkout` | delegates to the factory. A method call, not a construction — silent |
| `orders.CheckoutService.quick_receipt` | a shortcut: `Receipt{total}` outside the designated factory. **The violation.** |

Every element has a line. An element nobody can justify is an element to delete.

## Expected output

`outputs/findings.json` — One row per finding, sorted by `(rule, element, detail)`. `element` is the class the finding is attributed to; `detail` is the stable discriminator (`method->Type` for a construction, `method.field` for a reassignment) that lets two findings of one rule on one class carry different review keys.

```json
[
  {
    "detail": "quick_receipt->Receipt",
    "element": "orders.CheckoutService",
    "rule": "factory"
  }
]
```

**Deliberately absent:** messages, file paths and line numbers. A rule's `message:` is prose that gets rewritten, a path is a Windows/POSIX hazard, and a line number moves when someone adds a comment. What the baseline pins is the *identity* of each finding.

## Baseline provenance

**Computed by hand** from the constraint's definition in the catalogue, then checked against the engine. The walkthrough below is the derivation: every row in the baseline appears in it, and no row appears that the walkthrough does not produce.

## Walkthrough

### The rules, stated once

1. The `tag-conformance` rule **re-parses the source and reads method bodies**. It never consults the reference model or the diff, so it needs no baseline: the question is not "did intent drift" but "does this code obey its tags right now".
2. Construction detection in this language is **precise**. A construction is a composite literal — grammar node type `struct`, as in `Money{amount = 1}` — plus `new(T)` / `make(T)` allocations. The grammar distinguishes it outright, so there is nothing to guess.
3. `creates:` holds **short type names**, not qualified names.
4. The tag may sit on the class or on a method; either way the **owning class** becomes the designated factory, and construction is permitted anywhere inside it.
5. The finding is attributed to the offending class, with the discriminator `{method}->{Type}`.
6. **A type may always construct itself.** Without that rule every `T.new` / inner constructor would be flagged, and the idiom would be unusable.

### Applying them

**Step 1 — build the factory index (clauses 3–4).** One entry: `Receipt` is owned by
`orders.ReceiptFactory`.

**Step 2 — find every construction of `Receipt` (clause 2).**

| Site | Expression | Inside the designated factory? | Verdict |
| --- | --- | --- | --- |
| `orders.ReceiptFactory.for_total` | `Receipt{total}` | ✅ | permitted (clause 4) |
| `orders.CheckoutService.checkout` | *(no construction — it calls the factory)* | — | silent |
| `orders.CheckoutService.quick_receipt` | `Receipt{total}` | ❌ | **Fires** |

**Step 3 — the finding (clause 5).** Attributed to `orders.CheckoutService`, discriminated
`quick_receipt->Receipt`. The method name is in the discriminator rather than in the element,
so the review key survives the method moving around the file.

**The intended fix** is visible in the case itself: `checkout` already does the right
thing. Route `quick_receipt` through the factory and the run goes green.

### Elements that produce nothing

| Element | Why it is absent from the output |
| --- | --- |
| `orders.ReceiptFactory.for_total` | This is the designated factory; clause 4 permits construction anywhere inside it. |
| `orders.CheckoutService.checkout` | Calling a method that returns a `Receipt` is not constructing one. |

## Why this proves the code is correct

- **It pins:** that the *owning class* of the tag becomes the designated factory, that construction is permitted anywhere inside it, and that delegating to the factory is not itself a construction.
- **It would catch:** a regression that flagged the factory's own construction (making the tag self-defeating), one that stopped recognising the language's construction idiom, or one that treated a method call returning the type as a construction.
- **It does not cover:** the tag placed on a *method* rather than a class (the owning class still becomes the factory), several `creates` entries, and the interaction with `@no_instantiation` — the bundled demos ship one line that trips both at once.

## How to run and debug

```bash
make test-case CASE=enforce/factory/odin
make debug-case CASE=enforce/factory/odin
```

**Start here:** breakpoint in `tests/case_runner.py::_run_enforce`, then step into the engine. Inspect `_factory_index(project)` — it maps a created type to the classes allowed to build it.

## When to change this case

A red run is a regression until proven otherwise — do not regenerate the baseline to get green. If the requirement genuinely changed, add a new case for the new behaviour and retire this one explicitly. Regenerating (`UPDATE_BASELINES=1 make test-case CASE=enforce/factory/odin`) produces a diff a human reads line by line, in a commit that changes baselines and nothing else.
