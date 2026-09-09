# `@locked` — deleting the frozen element (Python)

## What this proves

Deleting a locked element is a mutation too. The ledger entry has nowhere to land, and the violation kind is `removed` — distinct from `changed`, so the report tells a reviewer what actually happened.

**Engine:** C — freeze — `cdec lock check`  
**Constraint:** [`locked`](../../../../../../docs/RULES_CATALOGUE.md#locked)  
**Language:** Python  
**Runner:** `tests/case_runner.py::_run_lock`

## Inputs

| File | What it is |
| --- | --- |
| `inputs/case.yaml` | Engine and language — the ambient inputs, written down so nothing about the run is implicit |
| `inputs/src/orders/billing.py` | the class survives; the locked method is gone |
| `inputs/baseline/orders/billing.py` | the approved implementation |

### Why each element is there

| Element | Demonstrates |
| --- | --- |
| ``orders.Receipt.formatted`` | deleted outright. **The violation.** |
| ``orders.Receipt`` | still present, so this is a `removed` method rather than a vanished class |

Every element has a line. An element nobody can justify is an element to delete.

## Expected output

`outputs/lock_violations.json` — One row per lock violation, sorted by `(kind, target)`. An empty list is a meaningful baseline here: it asserts that the edit was invisible to the digest.

```json
[
  {
    "kind": "removed",
    "target": "orders.Receipt.formatted"
  }
]
```

**Deliberately absent:** messages, file paths and line numbers. A rule's `message:` is prose that gets rewritten, a path is a Windows/POSIX hazard, and a line number moves when someone adds a comment. What the baseline pins is the *identity* of each finding.

## Baseline provenance

**Computed by hand** from the constraint's definition in the catalogue, then checked against the engine. The walkthrough below is the derivation: every row in the baseline appears in it, and no row appears that the walkthrough does not produce.

## Walkthrough

### The rules, stated once

1. `cdec lock` answers a narrower question than the other engines: not "did intent drift" or "does the code obey the tag", but **did this body change at all**.
2. A lock is an **AST identity, not a line range**. The digest is taken over a normalised syntax tree, so position is irrelevant.
3. Comments are dropped, and docstrings too unless `lock.include_docstrings` is set.
4. The `@locked` tag itself is stripped **recursively** before digesting — including a method-level lock nested inside a locked class. Applying or removing a lock can therefore never change the digest it records.
5. Same-named siblings (overloads, `@property` + setter) are **grouped into one target** whose digest covers the whole group, so adding an overload to a locked name is itself a change.
6. The five violation kinds are `changed`, `missing`, `removed`, `unlocked` and `algo-mismatch`.

### Applying them

**Step 0 — build the ledger** from `inputs/baseline/`: one entry,
`orders.Receipt.formatted`.

**Step 1 — collect targets from `inputs/src/`.** `orders.Receipt` is still there, but it
has no `formatted` member, so no target of that name is discovered.

**Step 2 — the `removed` check (clause 6).**

| Ledger entry | Discovered in source? | Kind |
| --- | --- | --- |
| `orders.Receipt.formatted` | ❌ | **`removed`** |

**Step 3 — why the kinds are separate.** `changed` says "the wording you signed off on is
different"; `removed` says "it is gone". A reviewer's next action differs completely, and
a report that collapsed them into one kind would cost that reviewer a diff-read every
time.

Note the reported violation carries the *ledger's* file path, because there is no current
source location to point at — the same reason a `no-removed-classes` violation has no
file or line.

## Why this proves the code is correct

- **It pins:** that deletion is caught, and that it is reported as its own kind.
- **It would catch:** a regression that treated a missing target as "nothing to check" and passed — which would let anyone retire a locked implementation silently.
- **It does not cover:** renaming, which presents as `removed` plus a new unlocked target; see `tests/test_lock_engine.py`.

## How to run and debug

```bash
make test-case CASE=lock/locked/python/removed
make debug-case CASE=lock/locked/python/removed
```

**Start here:** breakpoint in `tests/case_runner.py::_run_lock`, then step into the engine. `by_name.get(name)` returning `None` in `check_locks` is the branch under test.

## When to change this case

A red run is a regression until proven otherwise — do not regenerate the baseline to get green. If the requirement genuinely changed, add a new case for the new behaviour and retire this one explicitly. Regenerating (`UPDATE_BASELINES=1 make test-case CASE=lock/locked/python/removed`) produces a diff a human reads line by line, in a commit that changes baselines and nothing else.
