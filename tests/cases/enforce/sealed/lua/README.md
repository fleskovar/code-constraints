# `@sealed` — a value object may not be extended (Lua)

## What this proves

`@sealed` is the one Engine B rule that needs **no body analysis**: it compares the tag against every other class's base list, cross-file, so it works the moment a language has a parser. This case pins that a subclass fires and that composition — the sanctioned alternative — does not.

**Engine:** B — conformance — the `tag-conformance` rule  
**Constraint:** [`sealed`](../../../../../docs/RULES_CATALOGUE.md#sealed)  
**Language:** Lua  
**Runner:** `tests/case_runner.py::_run_enforce`

## Inputs

| File | What it is |
| --- | --- |
| `inputs/case.yaml` | Engine and language — the ambient inputs, written down so nothing about the run is implicit |
| `inputs/src/orders/annotated.lua` | source under test |
| `inputs/src/orders/discounted.lua` | source under test |
| `inputs/src/orders/receipt.lua` | source under test |

### Why each element is there

| Element | Demonstrates |
| --- | --- |
| `orders.Receipt` | carries the tag. A value object whose invariants cannot survive being extended |
| `orders.Discounted` | `setmetatable({}, { __index = Receipt })`. **The violation.** |
| `orders.Annotated` | **composition** — holds a `Receipt` in a field rather than extending it. The sanctioned alternative, and silent |

Every element has a line. An element nobody can justify is an element to delete.

## Expected output

`outputs/findings.json` — One row per finding, sorted by `(rule, element, detail)`. `element` is the class the finding is attributed to; `detail` is the stable discriminator (`method->Type` for a construction, `method.field` for a reassignment) that lets two findings of one rule on one class carry different review keys.

```json
[
  {
    "detail": "base:Receipt",
    "element": "orders.Discounted",
    "rule": "sealed"
  }
]
```

**Deliberately absent:** messages, file paths and line numbers. A rule's `message:` is prose that gets rewritten, a path is a Windows/POSIX hazard, and a line number moves when someone adds a comment. What the baseline pins is the *identity* of each finding.

## Baseline provenance

**Computed by hand** from the constraint's definition in the catalogue, then checked against the engine. The walkthrough below is the derivation: every row in the baseline appears in it, and no row appears that the walkthrough does not produce.

## Walkthrough

### The rules, stated once

1. The `tag-conformance` rule **re-parses the source and reads method bodies**. It never consults the reference model or the diff, so it needs no baseline: the question is not "did intent drift" but "does this code obey its tags right now".
2. `sealed` is evaluated **structurally**, against the parsed `Project`, in `enforce/engine.py::_check_sealed` — not by a per-language body analyzer.
3. Matching is by **short name**. Parsers give textual base names rather than resolved qualified names, so a sealed `Receipt` protects against any base spelled `Receipt` or `x.y.Receipt`.
4. A class never counts as subclassing itself (`short != cls.name`).
5. The finding is attributed to the **subclass**, with the discriminator `base:{ShortName}` — so a class extending two sealed types produces two findings.

### Applying them

**Step 1 — index the sealed classes (clause 2).** One entry: short name `Receipt` →
`orders.Receipt`.

**Step 2 — scan every class's base list (clauses 3–4).**

| Class | Bases | Sealed short name present? |
| --- | --- | --- |
| `orders.Receipt` | `[]` | — (and clause 4 would exclude it anyway) |
| `orders.Annotated` | `[]` | ❌ — it holds a `Receipt`, it does not extend one |
| `orders.Discounted` | `['Receipt']` | ✅ **Fires** |

**Step 3 — the finding (clause 5).** Attributed to `orders.Discounted`, discriminated
`base:Receipt`. The subclass is named because the subclass is what has to change; the
sealed type is doing exactly what it was asked to.

Note that no method body was read to reach this answer. `sealed` is the reason
Tag conformance is useful on a language before anyone writes a body analyzer for it.

### Elements that produce nothing

| Element | Why it is absent from the output |
| --- | --- |
| `orders.Annotated` | Composition is not inheritance. Its `Receipt` field creates a *reference* edge, which `cdec check` can police, but never a base. |
| `orders.Receipt` | A class does not subclass itself (clause 4). |

### Lua-specific notes

Lua has no inheritance keyword either; an `__index` metatable is the idiom, and the parser recognises it as a base. Note the contrast inside `annotated.lua`: it calls `Receipt.new(...)` — construction, not subtyping — and stores the result in a field. Construction of a sealed type is fine; extending it is not.

## Why this proves the code is correct

- **It pins:** that `sealed` is cross-file and structural, that the finding lands on the subclass rather than the sealed type, and that holding an instance is never a violation.
- **It would catch:** a regression that only checked within one file, one that attributed the finding to the sealed class (making the message useless), or one that treated a field of the sealed type as inheritance.
- **It does not cover:** a class extending two sealed types, and the interaction with `frozen-rules` when the tag is deleted — see `check/frozen-rules/…` for that half.

## How to run and debug

```bash
make test-case CASE=enforce/sealed/lua
make debug-case CASE=enforce/sealed/lua
```

**Start here:** breakpoint in `tests/case_runner.py::_run_enforce`, then step into the engine. Step into `enforce/engine.py::_check_sealed` and inspect `sealed_names` against each `cls.bases`.

## When to change this case

A red run is a regression until proven otherwise — do not regenerate the baseline to get green. If the requirement genuinely changed, add a new case for the new behaviour and retire this one explicitly. Regenerating (`UPDATE_BASELINES=1 make test-case CASE=enforce/sealed/lua`) produces a diff a human reads line by line, in a commit that changes baselines and nothing else.
