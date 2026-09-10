# `@locked` — `lock.targets:` globs freeze untagged code (Python)

## What this proves

A lock does not have to come from a tag. `lock.targets:` globs in `.cdec/config.yaml` freeze code you would rather not — or cannot — annotate: generated modules, vendored files, a pricing subtree owned by another team. A glob-locked element is verified exactly like a tagged one.

**Engine:** C — freeze — the `implementation-locks` rule  
**Constraint:** [`locked`](../../../../../../docs/RULES_CATALOGUE.md#4--implementation-locks)  
**Language:** Python  
**Runner:** `tests/case_runner.py::_run_lock`

## Inputs

| File | What it is |
| --- | --- |
| `inputs/case.yaml` | Engine and language — the ambient inputs, written down so nothing about the run is implicit |
| `inputs/src/orders/pricing.py` | the tax rate changed |
| `inputs/baseline/orders/pricing.py` | the approved implementation — note it carries **no tag at all** |

### Why each element is there

| Element | Demonstrates |
| --- | --- |
| ``orders.pricing.compute_tax`` | a module-level function with no `@locked` tag. Frozen by the glob `orders.pricing.**`, and its rate changed from `0.2` to `0.25`. **The violation.** |

Every element has a line. An element nobody can justify is an element to delete.

## Expected output

`outputs/lock_violations.json` — One row per lock violation, sorted by `(kind, target)`. An empty list is a meaningful baseline here: it asserts that the edit was invisible to the digest.

```json
[
  {
    "kind": "changed",
    "target": "orders.pricing.compute_tax"
  }
]
```

**Deliberately absent:** messages, file paths and line numbers. A rule's `message:` is prose that gets rewritten, a path is a Windows/POSIX hazard, and a line number moves when someone adds a comment. What the baseline pins is the *identity* of each finding.

## Baseline provenance

**Computed by hand** from the constraint's definition in the catalogue, then checked against the engine. The walkthrough below is the derivation: every row in the baseline appears in it, and no row appears that the walkthrough does not produce.

## Walkthrough

### The rules, stated once

1. The `implementation-locks` rule answers a narrower question than the other rules: not "did intent drift" or "does the code obey the tag", but **did this body change at all**.
2. A lock is an **AST identity, not a line range**. The digest is taken over a normalised syntax tree, so position is irrelevant.
3. Comments are dropped, and docstrings too unless `lock.include_docstrings` is set.
4. The `@locked` tag itself is stripped **recursively** before digesting — including a method-level lock nested inside a locked class. Applying or removing a lock can therefore never change the digest it records.
5. Same-named siblings (overloads, `@property` + setter) are **grouped into one target** whose digest covers the whole group, so adding an overload to a locked name is itself a change.
6. The five violation kinds are `changed`, `missing`, `removed`, `unlocked` and `algo-mismatch`.
7. `lock.targets:` globs freeze by qualified name, with no tag in the source. `inputs/case.yaml` carries `targets:` here, which the runner passes through as `LockOptions.patterns` exactly as `.cdec/config.yaml` would.
8. Glob-locked entries are recorded with `via_pattern: true`, which exempts them from the `unlocked` check — there was never a tag to delete.
9. A **module-level function** carries the module stem in its target name (`orders.pricing.compute_tax`), because two modules in one package may define the same function name. Classes use the plain UML qualified name.

### Applying them

**Step 1 — resolve the glob (clause 7).** `orders.pricing.**` is normalised to
`orders.pricing.*`, with `.` treated as an ordinary character, so it matches the target
`orders.pricing.compute_tax`.

**Step 2 — build the ledger.** Digesting `inputs/baseline/` records that target with
`via_pattern: true`. Nothing in the source says `@locked` — the freeze lives entirely in
configuration.

**Step 3 — re-digest `inputs/src/`.** The literal `0.2` became `0.25`:

| Ledger entry | Tagged? | Digest matches? | Kind |
| --- | --- | --- | --- |
| `orders.pricing.compute_tax` | ❌ (glob) | ❌ | **`changed`** |

**Step 4 — the target name (clause 9).** Note it is `orders.pricing.compute_tax`, not
`orders.compute_tax`: the module stem is part of the identity for module-level functions.
Getting this wrong is the usual reason a glob "does not work" — the pattern is fine and
the name is not what the author assumed. `cdec lock list --all` prints the real names.

## Why this proves the code is correct

- **It pins:** that a glob freezes untagged code, that the digest check is identical either way, and that module-level functions carry their module stem.
- **It would catch:** a regression that only considered tagged elements when applying globs, or one that dropped the module stem from function target names, silently re-pointing every glob.
- **It does not cover:** `via_pattern` exempting glob entries from the `unlocked` check — asserted in `tests/test_lock_engine.py`.

## How to run and debug

```bash
make test-case CASE=lock/locked/python/glob
make debug-case CASE=lock/locked/python/glob
```

**Start here:** breakpoint in `tests/case_runner.py::_run_lock`, then step into the engine. `is_locked_target(target, patterns)` is the single predicate that unifies tagged and glob-locked elements.

## When to change this case

A red run is a regression until proven otherwise — do not regenerate the baseline to get green. If the requirement genuinely changed, add a new case for the new behaviour and retire this one explicitly. Regenerating (`UPDATE_BASELINES=1 make test-case CASE=lock/locked/python/glob`) produces a diff a human reads line by line, in a commit that changes baselines and nothing else.
