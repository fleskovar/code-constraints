# The reference gate — the whole public shape is frozen (TypeScript)

## What this proves

TypeScript has **no constraint tags and no implementation-lock support**, which makes the reference gate the strongest guarantee available to it — and it is a strong one, because it needs no annotation whatsoever. This case is the answer to "what can code-constraints do for my TypeScript project?".

**Engine:** D — reference gate — the `reference-architecture` rule  
**Constraint:** [`Reference deviations`](../../../../../docs/RULES_CATALOGUE.md#3--the-reference-gate)  
**Language:** TypeScript  
**Runner:** `tests/case_runner.py::_run_reference`

## Inputs

| File | What it is |
| --- | --- |
| `inputs/case.yaml` | Engine and language — the ambient inputs, written down so nothing about the run is implicit |
| `inputs/src/catalog/book.ts` | four deviations plus a new class |
| `inputs/baseline/catalog/book.ts` | the reference shape |

### Why each element is there

| Element | Demonstrates |
| --- | --- |
| `catalog.Book` | `class` → `abstract class` |
| `catalog.Book.rating` | a property that no longer exists |
| `catalog.Book.isbn` | a new property |
| `catalog.Book.pages` | the method gained a parameter |
| `catalog.Series` | a new class |

Every element has a line. An element nobody can justify is an element to delete.

## Expected output

`outputs/deviations.json` — One row per structural deviation, sorted by `(element, member, category)`.

```json
[
  {
    "category": "class-kind-changed",
    "element": "catalog.Book"
  },
  {
    "category": "attribute-added",
    "element": "catalog.Book",
    "member": "isbn:string"
  },
  {
    "category": "operation-signature-changed",
    "element": "catalog.Book",
    "member": "pages(hardback:boolean):number"
  },
  {
    "category": "attribute-removed",
    "element": "catalog.Book",
    "member": "rating:number"
  },
  {
    "category": "class-added",
    "element": "catalog.Series"
  }
]
```

**Deliberately absent:** messages, file paths and line numbers. A rule's `message:` is prose that gets rewritten, a path is a Windows/POSIX hazard, and a line number moves when someone adds a comment. What the baseline pins is the *identity* of each finding.

## Baseline provenance

**Computed by hand** from the constraint's definition in the catalogue, then checked against the engine. The walkthrough below is the derivation: every row in the baseline appears in it, and no row appears that the walkthrough does not produce.

## Walkthrough

### The rules, stated once

1. The `reference-architecture` rule is a **wall**, not a scalpel: any structural deviation from the committed `.cdec/reference.xmi` fails, with no per-rule configuration at all.
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
| `class Book` → `abstract class Book` | class kind differs (clause 5) | `class-kind-changed` |
| `rating: number` deleted | in the reference, not in the code | `attribute-removed` |
| `isbn: string` added | no reference attribute of that name | `attribute-added` |
| `pages()` → `pages(hardback)` | matched by name, parameters differ | `operation-signature-changed` |
| `Series` added | in the code, not in the reference | `class-added` |

**Step 2 — sort (clause 6)** by `(element, member, category)`, which is why the baseline
reads in qualified-name order rather than in the order the comparator walked.

**Step 3 — accepting a deviation.** The gate has no `ignore:` and no severity. When a
reviewer agrees a change is intended, the author runs `cdec reference update` — "snapshot
what the code *is*" — and commits the new `reference.xmi` in the same PR. (`cdec
reference set MODEL` is the other direction: "declare what the code *should become*".)

### TypeScript-specific notes

Together with the `rules.yaml` rules, this is the whole TypeScript story: parse → model → dependency and shape rules → reference gate. The `tag-conformance` and `implementation-locks` rules refuse TypeScript **by name** rather than reporting "nothing found", so an unsupported language and an untagged one are never confused.

## Why this proves the code is correct

- **It pins:** the matching strategy — classes and members by name — and therefore the categories the gate reports for each kind of edit.
- **It would catch:** a comparator that started matching members by signature (collapsing `operation-signature-changed` into a removed + added pair and losing the gate's whole advantage), or one that stopped comparing a field.
- **It does not cover:** `class-bases-changed`, overload-group comparison, and the `cdec reference update` / `reference set` write paths; see `tests/test_reference_compare.py`.

## How to run and debug

```bash
make test-case CASE=reference/gate/typescript
make debug-case CASE=reference/gate/typescript
```

**Start here:** breakpoint in `tests/case_runner.py::_run_reference`, then step into the engine. Step into `compare_to_reference(reference, current)` — the two `Project`s go in, the `Deviation` list comes out.

## When to change this case

A red run is a regression until proven otherwise — do not regenerate the baseline to get green. If the requirement genuinely changed, add a new case for the new behaviour and retire this one explicitly. Regenerating (`UPDATE_BASELINES=1 make test-case CASE=reference/gate/typescript`) produces a diff a human reads line by line, in a commit that changes baselines and nothing else.
