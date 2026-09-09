# The reference gate — modifiers and class kind the diff cannot see (C#)

## What this proves

Three of these four deviations are **invisible to `cdec check`**, even with `frozen-members` fully enabled: the diff engine matches members by signature and never compares modifiers or class kind. This case is the concrete answer to "why would I run the reference gate as well?".

**Engine:** D — reference gate — `cdec reference test`  
**Constraint:** [`Reference deviations`](../../../../../docs/RULES_CATALOGUE.md#3--the-reference-gate)  
**Language:** C#  
**Runner:** `tests/case_runner.py::_run_reference`

## Inputs

| File | What it is |
| --- | --- |
| `inputs/case.yaml` | Engine and language — the ambient inputs, written down so nothing about the run is implicit |
| `inputs/src/Catalog/Author.cs` | two modifier changes and a new property |
| `inputs/src/Catalog/Book.cs` | the same class, now abstract |
| `inputs/baseline/Catalog/Author.cs` | the reference contract |
| `inputs/baseline/Catalog/Book.cs` | a concrete class |

### Why each element is there

| Element | Demonstrates |
| --- | --- |
| `Catalog.Book` | `class` → `abstract class`. **`frozen-members` is structurally blind to this** — no member changed |
| `Catalog.Author.Books` | `public` → `private`. Same signature, same return type |
| `Catalog.Author.Format` | instance → `static`. Again, the signature is untouched |
| `Catalog.Author.TestVar` | a plain new property, for contrast — the one deviation `cdec check` *would* also have caught |

Every element has a line. An element nobody can justify is an element to delete.

## Expected output

`outputs/deviations.json` — One row per structural deviation, sorted by `(element, member, category)`.

```json
[
  {
    "category": "operation-modifier-changed",
    "element": "Catalog.Author",
    "member": "Books():List<Book>"
  },
  {
    "category": "operation-modifier-changed",
    "element": "Catalog.Author",
    "member": "Format():string"
  },
  {
    "category": "attribute-added",
    "element": "Catalog.Author",
    "member": "TestVar:float"
  },
  {
    "category": "class-kind-changed",
    "element": "Catalog.Book"
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
| `class Book` → `abstract class Book` | class kind differs (clause 5). No member changed, so the diff engine sees nothing | `class-kind-changed` |
| `public List<Book> Books()` → `private` | same signature, access level differs | `operation-modifier-changed` |
| `public string Format()` → `public static` | same signature, static differs | `operation-modifier-changed` |
| `float TestVar` added | no reference attribute of that name | `attribute-added` |

**Step 2 — sort (clause 6)** by `(element, member, category)`, which is why the baseline
reads in qualified-name order rather than in the order the comparator walked.

**Step 3 — accepting a deviation.** The gate has no `ignore:` and no severity. When a
reviewer agrees a change is intended, the author runs `cdec reference update` — "snapshot
what the code *is*" — and commits the new `reference.xmi` in the same PR. (`cdec
reference set MODEL` is the other direction: "declare what the code *should become*".)

### C#-specific notes

This is the case to read when deciding whether to adopt the gate. `frozen-members` protects *which members exist and what they are called*; the gate additionally protects *what they are* — public vs private, instance vs static, concrete vs abstract. A `public` → `private` flip on a published API is a breaking change that `cdec check` will wave through.

## Why this proves the code is correct

- **It pins:** the matching strategy — classes and members by name — and therefore the categories the gate reports for each kind of edit.
- **It would catch:** a comparator that stopped checking `kind`, `visibility` or `is_static` — each of which would silently reopen a hole `cdec check` cannot cover.
- **It does not cover:** `class-bases-changed`, overload-group comparison, and the `cdec reference update` / `reference set` write paths; see `tests/test_reference_compare.py`.

## How to run and debug

```bash
make test-case CASE=reference/gate/csharp
make debug-case CASE=reference/gate/csharp
```

**Start here:** breakpoint in `tests/case_runner.py::_run_reference`, then step into the engine. Step into `compare_to_reference(reference, current)` — the two `Project`s go in, the `Deviation` list comes out.

## When to change this case

A red run is a regression until proven otherwise — do not regenerate the baseline to get green. If the requirement genuinely changed, add a new case for the new behaviour and retire this one explicitly. Regenerating (`UPDATE_BASELINES=1 make test-case CASE=reference/gate/csharp`) produces a diff a human reads line by line, in a commit that changes baselines and nothing else.
