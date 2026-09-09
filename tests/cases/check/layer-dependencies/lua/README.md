# `layer-dependencies` — the domain depends on nothing (Lua)

## What this proves

`layer-dependencies` reads `@layer` tags rather than directories, so it expresses a whole layering policy as one allow-matrix. This case pins the three semantics that surprise people: same-layer edges are always free, `domain: []` means "depend on nothing else", and a reference **to an untagged class is invisible**.

**Engine:** A — drift — `cdec check`  
**Constraint:** [`layer-dependencies`](../../../../../docs/RULES_CATALOGUE.md#layer-dependencies)  
**Language:** Lua  
**Runner:** `tests/case_runner.py::_run_check`

## Inputs

| File | What it is |
| --- | --- |
| `inputs/case.yaml` | Engine and language — the ambient inputs, written down so nothing about the run is implicit |
| `inputs/rules.yaml` | One rule entry carrying the `allow:` matrix — the whole layering policy in one place |
| `inputs/src/app/handler.lua` | the application layer |
| `inputs/src/domain/order.lua` | the violating table |
| `inputs/src/infrastructure/record.lua` | the forbidden target |

### Why each element is there

| Element | Demonstrates |
| --- | --- |
| `domain.Order` | `---@cdec layer("domain")`, and its metatable base is an infrastructure table. **The violation.** |
| `infrastructure.SqlRecord` | `---@cdec layer("infrastructure")` — the forbidden target |
| `app.CheckoutHandler` | `---@cdec layer("application")` → domain, allowed |

Every element has a line. An element nobody can justify is an element to delete.

## Expected output

`outputs/violations.json` — One row per violation, sorted by `(rule, element, member)`. `element` is the qualified name the violation is attributed to; `member` is the discriminating signature the review key is derived from.

```json
[
  {
    "element": "domain.Order",
    "member": "domain->infrastructure:infrastructure.SqlRecord",
    "rule": "layering",
    "severity": "error"
  }
]
```

**Deliberately absent:** messages, file paths and line numbers. A rule's `message:` is prose that gets rewritten, a path is a Windows/POSIX hazard, and a line number moves when someone adds a comment. What the baseline pins is the *identity* of each finding.

## Baseline provenance

**Computed by hand** from the constraint's definition in the catalogue, then checked against the engine. The walkthrough below is the derivation: every row in the baseline appears in it, and no row appears that the walkthrough does not produce.

## Walkthrough

### The rules, stated once

1. A class **A references B** when an attribute type, an operation parameter or return type, a body-level dependency recorded by the parser, or a base class of A resolves to B. Collection wrappers are unwrapped, so `list[B]` / `List<B>` / `B[]` all resolve to `B`.
2. A class's layer comes from its `@layer("name")` tag. Quotes are stripped, so every language's spelling agrees.
3. **Same-layer references are always allowed**, whatever the matrix says.
4. A class whose layer is **not a key** in `allow:` is left entirely unconstrained. `domain: []` is how you say "this layer may depend on nothing else".
5. A reference **to an untagged class is ignored** — the rule can only reason about tagged targets. This is the documented hole in the matrix.
6. The violation is attributed to the source class, with the discriminator `{source_layer}->{target_layer}:{target}`.

### Applying them

**Step 1 — read the layer tags (clause 2).** Then walk every outgoing reference of every
tagged class and consult the matrix.

| Edge | Source layer | Target layer | Verdict |
| --- | --- | --- | --- |
| `domain.Order -> infrastructure.SqlRecord` | domain | infrastructure | ❌ `domain: []`. **Fires.** |
| `app.CheckoutHandler -> domain.Order` | application | domain | ✅ allowed |

**Step 2 — the matrix, restated:**

```yaml
application: [domain]      # may reach down one level
domain:      []            # may reach nothing else
infrastructure: [domain]   # dependency inversion: implementations point at the port
```

**Step 3 — the finding (clause 6):** attributed to the source class, discriminated by
`{source_layer}->{target_layer}:{target}`, so a class that violates two layers at
once produces two independently waivable findings.

### Elements that produce nothing

| Element | Why it is absent from the output |
| --- | --- |
| `app.CheckoutHandler` | `application: [domain]` permits it. |

### Lua-specific notes

Because Lua fields are untyped, the reference the rule sees here is the **inheritance edge**: `domain.Order` derives from an `infrastructure` table. A domain type inheriting persistence is the classic layering smell this matrix exists to reject, so the case is realistic as well as convenient. Like Odin, Lua carries tags in `---@cdec` comments that must be line-adjacent to the declaration.

## Why this proves the code is correct

- **It pins:** that layers come from tags rather than directories, that same-layer edges are free, that an empty allow-list means "nothing", and that untagged targets are invisible.
- **It would catch:** a regression that started flagging same-layer edges, one that treated a missing `allow:` key as "deny all" instead of "unconstrained", or one that guessed a layer for untagged classes.
- **It does not cover:** a class whose layer is absent from `allow:` entirely, transitive layering, and the `ignore:` option; see `tests/test_lint_engine.py`.

## How to run and debug

```bash
make test-case CASE=check/layer-dependencies/lua
make debug-case CASE=check/layer-dependencies/lua
```

**Start here:** breakpoint in `tests/case_runner.py::_run_check`, then step into the engine. Inspect `layer_by_qn` inside the rule — it is the tag scan.

## When to change this case

A red run is a regression until proven otherwise — do not regenerate the baseline to get green. If the requirement genuinely changed, add a new case for the new behaviour and retire this one explicitly. Regenerating (`UPDATE_BASELINES=1 make test-case CASE=check/layer-dependencies/lua`) produces a diff a human reads line by line, in a commit that changes baselines and nothing else.
