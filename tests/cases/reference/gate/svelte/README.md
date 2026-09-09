# The reference gate — the whole public shape is frozen (Svelte 5)

## What this proves

A Svelte **component is a class** in the model, and its runes are attributes — so the reference gate freezes component state and props alongside ordinary logic modules, with no annotation. Svelte has no tags and no lock support, so this and the `rules.yaml` rules are its whole enforcement surface.

**Engine:** D — reference gate — `cdec reference test`  
**Constraint:** [`Reference deviations`](../../../../../docs/RULES_CATALOGUE.md#3--the-reference-gate)  
**Language:** Svelte 5  
**Runner:** `tests/case_runner.py::_run_reference`

## Inputs

| File | What it is |
| --- | --- |
| `inputs/case.yaml` | Engine and language — the ambient inputs, written down so nothing about the run is implicit |
| `inputs/src/lib/cart.ts` | three deviations |
| `inputs/src/routes/CartView.svelte` | a new piece of component state |
| `inputs/baseline/lib/cart.ts` | the reference shape of a logic module |
| `inputs/baseline/routes/CartView.svelte` | the reference shape of a component |

### Why each element is there

| Element | Demonstrates |
| --- | --- |
| `lib.Cart.currency` | a property that no longer exists |
| `lib.Cart.taxRate` | a new property |
| `lib.Cart.total` | the method gained a parameter |
| `routes.CartView.count` | a new `$state` rune in the component — components are compared exactly like classes |

Every element has a line. An element nobody can justify is an element to delete.

## Expected output

`outputs/deviations.json` — One row per structural deviation, sorted by `(element, member, category)`.

```json
[
  {
    "category": "attribute-removed",
    "element": "lib.Cart",
    "member": "currency:string"
  },
  {
    "category": "attribute-added",
    "element": "lib.Cart",
    "member": "taxRate:number"
  },
  {
    "category": "operation-signature-changed",
    "element": "lib.Cart",
    "member": "total(precision:number):number"
  },
  {
    "category": "attribute-added",
    "element": "routes.CartView",
    "member": "count:number"
  }
]
```

**Deliberately absent:** messages, file paths and line numbers. A rule's `message:` is prose that gets rewritten, a path is a Windows/POSIX hazard, and a line number moves when someone adds a comment. What the baseline pins is the *identity* of each finding.

## Baseline provenance

**Computed by hand** from the constraint's definition in the catalogue, then checked against the engine. The walkthrough below is the derivation: every row in the baseline appears in it, and no row appears that the walkthrough does not produce.

## Walkthrough

### The rules, stated once

1. `cdec reference test` is a **wall**, not a scalpel: any structural deviation from the committed `.cdec/reference.xmi` fails, with no per-rule configuration at all.
2. It runs a **dedicated field-by-field comparator** (`reference/compare.py`), not the diff engine — which is why it catches things `frozen-members` structurally cannot.
3. Classes are matched by **qualified name**; attributes by **name within the class**; operations by **name within the class**, with a full-signature fallback for overload groups.
4. **Because operations match by name, a changed parameter list reads as one `operation-signature-changed`** — not as the removed + added pair `frozen-members` produces. The messages are meant to read as "changed", and this is the price and the point.
5. `attribute-changed` covers type, access level, static, readonly and default value. `operation-modifier-changed` covers access level, static and abstract.
6. Deviations are sorted by `(qualified_name, member, category)`.

### Applying them

**Step 1 — walk both projects field by field (clauses 2–3).** `inputs/baseline/` is the
reference, `inputs/src/` is the current code.

| Edit | Why it deviates | Category |
| --- | --- | --- |
| `currency: string` deleted | in the reference, not in the code | `attribute-removed` |
| `taxRate: number` added | no reference attribute of that name | `attribute-added` |
| `total()` → `total(precision)` | matched by name, parameters differ | `operation-signature-changed` |
| `let count: number = $state(0)` added | component state is an attribute of the component class | `attribute-added` |

**Step 2 — sort (clause 6)** by `(element, member, category)`, which is why the baseline
reads in qualified-name order rather than in the order the comparator walked.

**Step 3 — accepting a deviation.** The gate has no `ignore:` and no severity. When a
reviewer agrees a change is intended, the author runs `cdec reference update` — "snapshot
what the code *is*" — and commits the new `reference.xmi` in the same PR. (`cdec
reference set MODEL` is the other direction: "declare what the code *should become*".)

### Svelte 5-specific notes

Adding `let count: number = $state(0)` is a real API change to a component in the sense the gate cares about: it is state the component now owns. Note that `$props()` destructuring also becomes attributes (typed `$props`), so a component's *public* interface — the props it accepts — is frozen by the same mechanism. That is the closest thing Svelte has to a signature.

## Why this proves the code is correct

- **It pins:** the matching strategy — classes and members by name — and therefore the categories the gate reports for each kind of edit.
- **It would catch:** a comparator that started matching members by signature (collapsing `operation-signature-changed` into a removed + added pair and losing the gate's whole advantage), or one that stopped comparing a field.
- **It does not cover:** `class-bases-changed`, overload-group comparison, and the `cdec reference update` / `reference set` write paths; see `tests/test_reference_compare.py`.

## How to run and debug

```bash
make test-case CASE=reference/gate/svelte
make debug-case CASE=reference/gate/svelte
```

**Start here:** breakpoint in `tests/case_runner.py::_run_reference`, then step into the engine. Step into `compare_to_reference(reference, current)` — the two `Project`s go in, the `Deviation` list comes out.

## When to change this case

A red run is a regression until proven otherwise — do not regenerate the baseline to get green. If the requirement genuinely changed, add a new case for the new behaviour and retire this one explicitly. Regenerating (`UPDATE_BASELINES=1 make test-case CASE=reference/gate/svelte`) produces a diff a human reads line by line, in a commit that changes baselines and nothing else.
