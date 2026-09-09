# `@immutable` — no field reassignment after construction (C#)

## What this proves

`@immutable` fires when a method **other than the constructor** assigns to one of the class's own fields. This case pins all three shapes side by side: constructor initialisation (silent), a read-only method (silent), a "modification" that returns a new instance (silent), and one reassignment (the violation).

**Engine:** B — conformance — `cdec enforce`  
**Constraint:** [`immutable`](../../../../../docs/RULES_CATALOGUE.md#immutable)  
**Language:** C#  
**Runner:** `tests/case_runner.py::_run_enforce`

## Inputs

| File | What it is |
| --- | --- |
| `inputs/case.yaml` | Engine and language — the ambient inputs, written down so nothing about the run is implicit |
| `inputs/src/Orders/Receipt.cs` | source under test |

### Why each element is there

| Element | Demonstrates |
| --- | --- |
| `Orders.Receipt (constructor / `new`)` | assigns every field. Initialisation, not mutation — silent |
| `Orders.Receipt.with_discount` | the sanctioned "modification": builds and returns a **new** instance, assigns nothing |
| `Orders.Receipt.formatted` | reads fields only — silent |
| `Orders.Receipt.ApplyDiscount` | reassigns `_total` outside the constructor. **The violation.** |

Every element has a line. An element nobody can justify is an element to delete.

## Expected output

`outputs/findings.json` — One row per finding, sorted by `(rule, element, detail)`. `element` is the class the finding is attributed to; `detail` is the stable discriminator (`method->Type` for a construction, `method.field` for a reassignment) that lets two findings of one rule on one class carry different review keys.

```json
[
  {
    "detail": "ApplyDiscount._total",
    "element": "Orders.Receipt",
    "rule": "immutable"
  }
]
```

**Deliberately absent:** messages, file paths and line numbers. A rule's `message:` is prose that gets rewritten, a path is a Windows/POSIX hazard, and a line number moves when someone adds a comment. What the baseline pins is the *identity* of each finding.

## Baseline provenance

**Computed by hand** from the constraint's definition in the catalogue, then checked against the engine. The walkthrough below is the derivation: every row in the baseline appears in it, and no row appears that the walkthrough does not produce.

## Walkthrough

### The rules, stated once

1. `cdec enforce` **re-parses the source and reads method bodies**. It never consults the reference model or the diff, so it needs no baseline: the question is not "did intent drift" but "does this code obey its tags right now".
2. A violation is an assignment whose **target is a field of the receiver** — `self.x` / `this.x` / `r.x` where `r` is the receiver parameter. An assignment to some *other* object's field is not a violation.
3. The constructor is exempt: assignment there is *initialisation*. Here that means any member that is not a `constructor_declaration`.
4. The finding is attributed to the **class**, with the discriminator `{method}.{field}` — so two different methods mutating the same field, or one method mutating two fields, are separate findings with separate review keys.
5. C# also catches a **bare** assignment to a known field name, not just `this.x`.

### Applying them

**Step 1 — find the tagged class (clause 1).** `Orders.Receipt` carries `immutable`.

**Step 2 — walk each of its methods, looking for assignment to a receiver field
(clauses 2–3).**

| Method | Assigns to a receiver field? | Exempt? | Verdict |
| --- | --- | --- | --- |
| constructor / `new` | ✅ both fields | ✅ clause 3 | silent |
| `with_discount` | ❌ — it *constructs* and returns | — | silent |
| `formatted` | ❌ — reads only | — | silent |
| `ApplyDiscount` | ✅ `_total` | ❌ | **Fires** |

**Step 3 — the finding (clause 4).** Attributed to `Orders.Receipt`, discriminated
`ApplyDiscount._total`. Both halves matter: a reviewer waiving one method's mutation is not
silently waiving another's.

The three silent rows are the point of the case. A rule that only ever fires teaches
nothing; these show what the sanctioned shapes look like, and `with_discount` in
particular is the answer to "but I need to change it".

### Elements that produce nothing

| Element | Why it is absent from the output |
| --- | --- |
| `Orders.Receipt.with_discount` | It returns a new instance. This is what "modifying" an immutable value looks like. |
| `Orders.Receipt.formatted` | Reads are always free. |
| `the constructor` | Exempt by clause 3 (any member that is not a `constructor_declaration`). |

### C#-specific notes

Two C#-specific footguns live in this analyzer. An arrow-bodied method exposes its `arrow_expression_clause` as the `body` field, so collecting both the body field and the arrow children double-counts — the analyzer dedupes by node id. And `this.field` access uses a node of type `this`, not `this_expression`. This case uses private fields rather than get-only properties so the assignment target is unambiguous.

## Why this proves the code is correct

- **It pins:** that constructor initialisation is exempt, that returning a new instance is the sanctioned alternative, that reads are free, and that the discriminator names both the method and the field.
- **It would catch:** a regression that started flagging constructor assignment (making the tag unusable), one that flagged assignment to a local or to another object's field, or one that dropped the field from the discriminator so two mutations collapsed into one waiver.
- **It does not cover:** augmented assignment in every language, annotated assignment, and mutation through a method call (`self.items.append(x)`), which no analyzer here detects — `@immutable` is about *rebinding fields*, not deep immutability.

## How to run and debug

```bash
make test-case CASE=enforce/immutable/csharp
make debug-case CASE=enforce/immutable/csharp
```

**Start here:** breakpoint in `tests/case_runner.py::_run_enforce`, then step into the engine. Break in the language's `conformance.py::analyze` and watch which assignment nodes are visited.

## When to change this case

A red run is a regression until proven otherwise — do not regenerate the baseline to get green. If the requirement genuinely changed, add a new case for the new behaviour and retire this one explicitly. Regenerating (`UPDATE_BASELINES=1 make test-case CASE=enforce/immutable/csharp`) produces a diff a human reads line by line, in a commit that changes baselines and nothing else.
