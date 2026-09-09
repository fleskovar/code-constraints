# `@locked` — deleting the tag does not escape the lock (Python)

## What this proves

**The ledger is the authority, not the source.** Removing the `@locked` tag from an element that is already in `.cdec/locks.yaml` is reported as `unlocked` — otherwise escaping a lock would be a one-line edit and the whole feature would be theatre.

**Engine:** C — freeze — `cdec lock check`  
**Constraint:** [`locked`](../../../../../../docs/RULES_CATALOGUE.md#locked)  
**Language:** Python  
**Runner:** `tests/case_runner.py::_run_lock`

## Inputs

| File | What it is |
| --- | --- |
| `inputs/case.yaml` | Engine and language — the ambient inputs, written down so nothing about the run is implicit |
| `inputs/src/orders/billing.py` | the identical body with the tag deleted |
| `inputs/baseline/orders/billing.py` | the approved implementation, tagged |

### Why each element is there

| Element | Demonstrates |
| --- | --- |
| ``orders.Receipt.formatted`` | still exists, body **unchanged** — only `@locked(reason=...)` was deleted. **The violation.** |

Every element has a line. An element nobody can justify is an element to delete.

## Expected output

`outputs/lock_violations.json` — One row per lock violation, sorted by `(kind, target)`. An empty list is a meaningful baseline here: it asserts that the edit was invisible to the digest.

```json
[
  {
    "kind": "unlocked",
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

**Step 0 — build the ledger.** **This case folder contains no sha256.** `inputs/baseline/` is the source as it stood when the lock was approved; the runner digests it to build the ledger, then verifies `inputs/src/` against that. So the "approved digest" is something a reader can see and reason about, and a fingerprinter change shows up as a real diff rather than as a stale opaque hash. It records `orders.Receipt.formatted`.

**Step 1 — what changed.** Only the tag. The body is byte-identical, so the *digest*
still matches — this is emphatically not a `changed` violation.

**Step 2 — the `unlocked` check (clause 6).** `check_locks` walks the ledger and finds
`orders.Receipt.formatted` still present in the source but no longer carrying the tag. Because the ledger
is the authority, that is a violation in its own right.

| Ledger entry | Element exists? | Still tagged? | Digest matches? | Kind |
| --- | --- | --- | --- | --- |
| `orders.Receipt.formatted` | ✅ | ❌ | ✅ | **`unlocked`** |

**Step 3 — the escape that is not one.** The fix is *not* to delete the ledger entry by
hand; it is `cdec lock set --target orders.Receipt.formatted --force`, which prunes the entry and leaves
a reviewable diff. `update_locks` freely *adds* locks without `--force`, but will not
prune or re-baseline without it — so `cdec lock set` stays safe for anyone to run and can
never erase evidence.

> **Glob-locked entries are exempt from this check**, because they were never declared by
> a tag in the first place. See `lock/locked/python/glob-targets-freeze-untagged-code`.

## Why this proves the code is correct

- **It pins:** that the ledger outranks the source, and that an untagged-but-ledgered element is a violation even when its body is untouched.
- **It would catch:** the obvious bypass — deleting the tag to silence a lock — and a regression that made `unlocked` fire on glob-locked entries, which would make `lock.targets:` unusable.
- **It does not cover:** the `--force` prune path itself; see `tests/test_lock_cli.py`.

## How to run and debug

```bash
make test-case CASE=lock/locked/python/unlocked
make debug-case CASE=lock/locked/python/unlocked
```

**Start here:** breakpoint in `tests/case_runner.py::_run_lock`, then step into the engine. Look at `LockEntry.via_pattern` — that flag is what exempts glob-locked entries from this check.

## When to change this case

A red run is a regression until proven otherwise — do not regenerate the baseline to get green. If the requirement genuinely changed, add a new case for the new behaviour and retire this one explicitly. Regenerating (`UPDATE_BASELINES=1 make test-case CASE=lock/locked/python/unlocked`) produces a diff a human reads line by line, in a commit that changes baselines and nothing else.
