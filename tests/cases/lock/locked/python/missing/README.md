# `@locked` — declared but never baselined (Python)

## What this proves

An element tagged `@locked` that has **no ledger entry** is reported `missing`. Nothing is actually being verified, so a silent pass would be the worst possible outcome: the code would look protected and be wide open.

**Engine:** C — freeze — the `implementation-locks` rule  
**Constraint:** [`locked`](../../../../../../docs/RULES_CATALOGUE.md#locked)  
**Language:** Python  
**Runner:** `tests/case_runner.py::_run_lock`

## Inputs

| File | What it is |
| --- | --- |
| `inputs/case.yaml` | Engine and language — the ambient inputs, written down so nothing about the run is implicit |
| `inputs/src/orders/billing.py` | a tagged element with no approved digest anywhere |

### Why each element is there

| Element | Demonstrates |
| --- | --- |
| ``orders.Receipt.formatted`` | carries `@locked(reason=...)`, but the ledger is empty. **The violation.** |

Every element has a line. An element nobody can justify is an element to delete.

## Expected output

`outputs/lock_violations.json` — One row per lock violation, sorted by `(kind, target)`. An empty list is a meaningful baseline here: it asserts that the edit was invisible to the digest.

```json
[
  {
    "kind": "missing",
    "target": "orders.Receipt.formatted"
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

### Applying them

**Step 0 — the ledger is empty.** This case has **no `inputs/baseline/`**, which is how
it stages the situation: someone added a `@locked` tag and never ran `cdec check --automatic-exceptions locks`.

**Step 1 — collect declared targets (clause 1).** One: `orders.Receipt.formatted`, with
`declared=True` because it carries the tag.

**Step 2 — the `missing` check (clause 6).**

| Declared target | In the ledger? | Kind |
| --- | --- | --- |
| `orders.Receipt.formatted` | ❌ | **`missing`** |

**Step 3 — why this is a violation rather than a warning.** The failure mode it prevents
is a reviewer seeing `@locked` in a diff, assuming the body is frozen, and approving. The
fix is one safe command — `cdec check --automatic-exceptions locks` — which anyone may run, because adding a lock
can never erase evidence of anything.

## Why this proves the code is correct

- **It pins:** that a tag with no ledger entry fails rather than passing silently.
- **It would catch:** a regression that only iterated the ledger (and so never noticed a tag nobody had baselined) — the most plausible way this check gets lost during a refactor.
- **It does not cover:** the ledger write path itself; see `tests/test_lock_cli.py`.

## How to run and debug

```bash
make test-case CASE=lock/locked/python/missing
make debug-case CASE=lock/locked/python/missing
```

**Start here:** breakpoint in `tests/case_runner.py::_run_lock`, then step into the engine. Note that `check_locks` iterates *both* the ledger and the discovered targets. This case exercises the second loop.

## When to change this case

A red run is a regression until proven otherwise — do not regenerate the baseline to get green. If the requirement genuinely changed, add a new case for the new behaviour and retire this one explicitly. Regenerating (`UPDATE_BASELINES=1 make test-case CASE=lock/locked/python/missing`) produces a diff a human reads line by line, in a commit that changes baselines and nothing else.
