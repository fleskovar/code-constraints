# The reference gate — the whole public shape is frozen (Python)

## What this proves

The reference gate freezes the **whole public shape** with zero configuration. This case exercises six deviation categories at once and — most importantly — shows that a changed parameter list is **one** `operation-signature-changed`, the direct contrast with `frozen-members`, which reports the same edit as a removed + added pair.

**Engine:** D — reference gate — `cdec reference test`  
**Constraint:** [`Reference deviations`](../../../../../docs/RULES_CATALOGUE.md#3--the-reference-gate)  
**Language:** Python  
**Runner:** `tests/case_runner.py::_run_reference`

## Inputs

| File | What it is |
| --- | --- |
| `inputs/case.yaml` | Engine and language — the ambient inputs, written down so nothing about the run is implicit |
| `inputs/src/catalog/author.py` | four separate deviations |
| `inputs/src/catalog/book.py` | internals rewritten, shape identical |
| `inputs/src/catalog/series.py` | a class the reference does not have |
| `inputs/baseline/catalog/author.py` | the reference contract |
| `inputs/baseline/catalog/book.py` | unchanged public shape |
| `inputs/baseline/catalog/legacy.py` | a class the code no longer has |

### Why each element is there

| Element | Demonstrates |
| --- | --- |
| `catalog.Book` | internals rewritten, public shape identical — **silent**. The gate freezes shape, not behaviour |
| `catalog.Author.rating` | `int` → `float`: an attribute type change |
| `catalog.Author.books` | gained a parameter — one `operation-signature-changed`, **not** a removed + added pair |
| `catalog.Author.retired` | same parameters, `bool` → `str` return |
| `catalog.Author.followers` | a genuinely new method |
| `catalog.LegacyIndex` | in the reference, gone from the code |
| `catalog.Series` | in the code, absent from the reference |

Every element has a line. An element nobody can justify is an element to delete.

## Expected output

`outputs/deviations.json` — One row per structural deviation, sorted by `(element, member, category)`.

```json
[
  {
    "category": "operation-signature-changed",
    "element": "catalog.Author",
    "member": "books(sort:bool):list[Book]"
  },
  {
    "category": "operation-added",
    "element": "catalog.Author",
    "member": "followers():int"
  },
  {
    "category": "attribute-changed",
    "element": "catalog.Author",
    "member": "rating:float"
  },
  {
    "category": "operation-return-type-changed",
    "element": "catalog.Author",
    "member": "retired():str"
  },
  {
    "category": "class-removed",
    "element": "catalog.LegacyIndex"
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
| `rating: int` → `rating: float` | same name, different type (clause 5) | `attribute-changed` |
| `books(self)` → `books(self, sort)` | matched by name, parameters differ (clause 4) | `operation-signature-changed` |
| `retired() -> bool` → `-> str` | same parameters, different return | `operation-return-type-changed` |
| `followers()` added | no reference operation of that name | `operation-added` |
| `LegacyIndex` deleted | in the reference, not in the code | `class-removed` |
| `Series` added | in the code, not in the reference | `class-added` |

**Step 2 — sort (clause 6)** by `(element, member, category)`, which is why the baseline
reads in qualified-name order rather than in the order the comparator walked.

**Step 3 — accepting a deviation.** The gate has no `ignore:` and no severity. When a
reviewer agrees a change is intended, the author runs `cdec reference update` — "snapshot
what the code *is*" — and commits the new `reference.xmi` in the same PR. (`cdec
reference set MODEL` is the other direction: "declare what the code *should become*".)

### Python-specific notes

Compare this case with `check/frozen-members/python/published-contract-signature`, which makes the *same* kind of edit to a method and reports it as two violations. Neither is wrong: `frozen-members` matches by signature so it can discriminate overloads, the gate matches by name so its messages read as "changed". Knowing which you are running is the difference between reading a report and guessing at one.

## Why this proves the code is correct

- **It pins:** the matching strategy — classes and members by name — and therefore the categories the gate reports for each kind of edit.
- **It would catch:** a comparator that started matching members by signature (collapsing `operation-signature-changed` into a removed + added pair and losing the gate's whole advantage), or one that stopped comparing a field.
- **It does not cover:** `class-bases-changed`, overload-group comparison, and the `cdec reference update` / `reference set` write paths; see `tests/test_reference_compare.py`.

## How to run and debug

```bash
make test-case CASE=reference/gate/python
make debug-case CASE=reference/gate/python
```

**Start here:** breakpoint in `tests/case_runner.py::_run_reference`, then step into the engine. Step into `compare_to_reference(reference, current)` — the two `Project`s go in, the `Deviation` list comes out.

## When to change this case

A red run is a regression until proven otherwise — do not regenerate the baseline to get green. If the requirement genuinely changed, add a new case for the new behaviour and retire this one explicitly. Regenerating (`UPDATE_BASELINES=1 make test-case CASE=reference/gate/python`) produces a diff a human reads line by line, in a commit that changes baselines and nothing else.
