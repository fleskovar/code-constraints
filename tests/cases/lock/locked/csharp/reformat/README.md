# `@locked` — reformatting does not trip a lock (C#)

## What this proves

A lock is an **AST identity, not a line range**. Moving the element, reformatting it, rewriting comments and docstrings, and inserting unrelated code above it all leave the digest untouched. An empty baseline is the assertion here — and it is the property the whole feature rests on, because without it `cdec lock` would fire on every reformat and teams would switch it off.

**Engine:** C — freeze — `cdec lock check`  
**Constraint:** [`locked`](../../../../../../docs/RULES_CATALOGUE.md#locked)  
**Language:** C#  
**Runner:** `tests/case_runner.py::_run_lock`

## Inputs

| File | What it is |
| --- | --- |
| `inputs/case.yaml` | Engine and language — the ambient inputs, written down so nothing about the run is implicit |
| `inputs/src/Orders/Billing.cs` | the same implementation, cosmetically rewritten |
| `inputs/baseline/Orders/Billing.cs` | the approved implementation |

### Why each element is there

| Element | Demonstrates |
| --- | --- |
| ``UnrelatedNewMethod`` | **inserted above** the locked method. Clause 2 |
| `the `Formatted` body` | expression body rewritten as a block body with the same statement |
| `a new `// comment`` | clause 3 drops comments |
| ``Orders.Receipt.Formatted`` | the locked method. Its body is **semantically identical** on both sides |

Every element has a line. An element nobody can justify is an element to delete.

## Expected output

`outputs/lock_violations.json` — One row per lock violation, sorted by `(kind, target)`. An empty list is a meaningful baseline here: it asserts that the edit was invisible to the digest.

```json
[]
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

**Step 0 — build the ledger.** **This case folder contains no sha256.** `inputs/baseline/` is the source as it stood when the lock was approved; the runner digests it to build the ledger, then verifies `inputs/src/` against that. So the "approved digest" is something a reader can see and reason about, and a fingerprinter change shows up as a real diff rather than as a stale opaque hash.

Digesting `inputs/baseline/` records one entry: target `Orders.Receipt.Formatted`, algo `cs-ts/1`.

**Step 1 — classify every edit in `inputs/src/` (clauses 2–4).**

| Edit | Why it is cosmetic | Effect on the digest |
| --- | --- | --- |
| `UnrelatedNewMethod` | **inserted above** the locked method. Clause 2 | invisible |
| the `Formatted` body | expression body rewritten as a block body with the same statement | invisible |
| a new `// comment` | clause 3 drops comments | invisible |
| the `@locked` tag | present on both sides | clause 4 strips it either way |

**Step 2 — re-digest and compare (clause 1).** The normalised tree is byte-identical, so
the digest matches the ledger and `check_locks` returns no violations.

**Step 3 — the baseline is `[]`.** An empty expected output is a real assertion, not an
absence of one: the case fails the moment any of the edits above starts moving the
digest.

### C#-specific notes

The C# fingerprinter serialises the tree-sitter subtree and **walks anonymous children too**: operators and punctuation are anonymous tokens, so skipping them would hash `a + b` and `a - b` identically. `comment` nodes are dropped explicitly — unlike Python, comments *are* nodes here.

## Why this proves the code is correct

- **It pins:** that position, whitespace, comments, docstrings and unrelated insertions are all outside the digest, and that applying the tag does not change what the tag records.
- **It would catch:** a fingerprinter that started including position attributes, one that stopped dropping comments, or one that failed to strip the `@locked` tag — any of which would make `cdec lock set` unable to record a stable baseline in the first place.
- **It does not cover:** `include_docstrings: true`, which deliberately *does* make docstring edits significant — see `tests/test_lock_fingerprint.py`.

## How to run and debug

```bash
make test-case CASE=lock/locked/csharp/reformat
make debug-case CASE=lock/locked/csharp/reformat
```

**Start here:** breakpoint in `tests/case_runner.py::_run_lock`, then step into the engine. Compare `collect_targets(baseline, "csharp")` with `collect_targets(src, "csharp")` and diff the two digests.

## When to change this case

A red run is a regression until proven otherwise — do not regenerate the baseline to get green. If the requirement genuinely changed, add a new case for the new behaviour and retire this one explicitly. Regenerating (`UPDATE_BASELINES=1 make test-case CASE=lock/locked/csharp/reformat`) produces a diff a human reads line by line, in a commit that changes baselines and nothing else.
