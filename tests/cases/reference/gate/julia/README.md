# The reference gate — the whole public shape is frozen (Julia)

## What this proves

Julia's public shape is its type fields and its method signatures, and the reference gate freezes both with no macros in the source at all. Note the doubly-nested qualified names — directory plus module — which is what a committed `reference.xmi` will contain.

**Engine:** D — reference gate — `cdec reference test`  
**Constraint:** [`Reference deviations`](../../../../../docs/RULES_CATALOGUE.md#3--the-reference-gate)  
**Language:** Julia  
**Runner:** `tests/case_runner.py::_run_reference`

## Inputs

| File | What it is |
| --- | --- |
| `inputs/case.yaml` | Engine and language — the ambient inputs, written down so nothing about the run is implicit |
| `inputs/src/catalog/Catalog.jl` | three deviations plus a new struct |
| `inputs/baseline/catalog/Catalog.jl` | the reference shape |

### Why each element is there

| Element | Demonstrates |
| --- | --- |
| `catalog.Catalog.Book.rating` | `Int` → `Float64`: a field type change |
| `catalog.Catalog.Book.isbn` | a new field |
| `catalog.Catalog.Book.pages` | the function gained a parameter |
| `catalog.Catalog.Series` | a new struct |

Every element has a line. An element nobody can justify is an element to delete.

## Expected output

`outputs/deviations.json` — One row per structural deviation, sorted by `(element, member, category)`.

```json
[
  {
    "category": "attribute-added",
    "element": "catalog.Catalog.Book",
    "member": "isbn:String"
  },
  {
    "category": "operation-signature-changed",
    "element": "catalog.Catalog.Book",
    "member": "pages(hardback:Bool):Int"
  },
  {
    "category": "attribute-changed",
    "element": "catalog.Catalog.Book",
    "member": "rating:Float64"
  },
  {
    "category": "class-added",
    "element": "catalog.Catalog.Series"
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
| `rating::Int` → `rating::Float64` | same name, different type | `attribute-changed` |
| `isbn::String` added | no reference field of that name | `attribute-added` |
| `pages(b)` → `pages(b, hardback)` | matched by name, parameters differ | `operation-signature-changed` |
| `Series` added | in the code, not in the reference | `class-added` |

**Step 2 — sort (clause 6)** by `(element, member, category)`, which is why the baseline
reads in qualified-name order rather than in the order the comparator walked.

**Step 3 — accepting a deviation.** The gate has no `ignore:` and no severity. When a
reviewer agrees a change is intended, the author runs `cdec reference update` — "snapshot
what the code *is*" — and commits the new `reference.xmi` in the same PR. (`cdec
reference set MODEL` is the other direction: "declare what the code *should become*".)

### Julia-specific notes

Adding a **method** to a Julia type means adding a function whose first parameter has that type — often in a different file from the struct. The parser is two-phase for exactly this reason (register every type, then attach), so the gate sees the same ownership a reader would. `Float64` and `Int` are compared as plain type text, not by Julia's type lattice: widening `Int` → `Float64` is a deviation even though every `Int` is a valid `Float64` argument.

## Why this proves the code is correct

- **It pins:** the matching strategy — classes and members by name — and therefore the categories the gate reports for each kind of edit.
- **It would catch:** a comparator that started matching members by signature (collapsing `operation-signature-changed` into a removed + added pair and losing the gate's whole advantage), or one that stopped comparing a field.
- **It does not cover:** `class-bases-changed`, overload-group comparison, and the `cdec reference update` / `reference set` write paths; see `tests/test_reference_compare.py`.

## How to run and debug

```bash
make test-case CASE=reference/gate/julia
make debug-case CASE=reference/gate/julia
```

**Start here:** breakpoint in `tests/case_runner.py::_run_reference`, then step into the engine. Step into `compare_to_reference(reference, current)` — the two `Project`s go in, the `Deviation` list comes out.

## When to change this case

A red run is a regression until proven otherwise — do not regenerate the baseline to get green. If the requirement genuinely changed, add a new case for the new behaviour and retire this one explicitly. Regenerating (`UPDATE_BASELINES=1 make test-case CASE=reference/gate/julia`) produces a diff a human reads line by line, in a commit that changes baselines and nothing else.
