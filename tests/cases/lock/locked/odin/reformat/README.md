# `@locked` — reformatting does not trip a lock (Odin)

## What this proves

A lock is an **AST identity, not a line range**. Moving the element, reformatting it, rewriting comments and docstrings, and inserting unrelated code above it all leave the digest untouched. An empty baseline is the assertion here — and it is the property the whole feature rests on, because without it `cdec lock` would fire on every reformat and teams would switch it off.

**Engine:** C — freeze — `cdec lock check`  
**Constraint:** [`locked`](../../../../../../docs/RULES_CATALOGUE.md#locked)  
**Language:** Odin  
**Runner:** `tests/case_runner.py::_run_lock`

## Inputs

| File | What it is |
| --- | --- |
| `inputs/case.yaml` | Engine and language — the ambient inputs, written down so nothing about the run is implicit |
| `inputs/src/billing/invoice.odin` | the same implementation, cosmetically rewritten |
| `inputs/baseline/billing/invoice.odin` | the approved implementation |

### Why each element is there

| Element | Demonstrates |
| --- | --- |
| ``UNRELATED :: 1`` | **inserted above** the locked proc. Clause 2 |
| `the `formatted` signature` | reformatted across several lines |
| `a new `// comment` in the body` | clause 3 drops comments |
| ``billing.Invoice.formatted`` | the locked proc. Its body is **semantically identical** on both sides |

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

Digesting `inputs/baseline/` records one entry: target `billing.Invoice.formatted`, algo `odin-ts/1`.

**Step 1 — classify every edit in `inputs/src/` (clauses 2–4).**

| Edit | Why it is cosmetic | Effect on the digest |
| --- | --- | --- |
| `UNRELATED :: 1` | **inserted above** the locked proc. Clause 2 | invisible |
| the `formatted` signature | reformatted across several lines | invisible |
| a new `// comment` in the body | clause 3 drops comments | invisible |
| the `@locked` tag | present on both sides | clause 4 strips it either way |

**Step 2 — re-digest and compare (clause 1).** The normalised tree is byte-identical, so
the digest matches the ledger and `check_locks` returns no violations.

**Step 3 — the baseline is `[]`.** An empty expected output is a real assertion, not an
absence of one: the case fails the moment any of the edits above starts moving the
digest.

> ⚠️ **One real limitation, found while writing this case.** `odin-ts/1` serialises
> anonymous tokens — it has to, or `a + b` and `a - b` would hash alike — and a
> **trailing comma** in a parameter list is one of them. So reformatting
> `proc(inv: ^Invoice)` to a multi-line form *with* a trailing comma does move the
> digest, even though the edit is purely cosmetic in Odin. This case deliberately omits
> the trailing comma so that it asserts the guarantee the tool actually gives. If you hit
> a `changed` violation you cannot explain, check for a comma.

### Odin-specific notes

Odin, Lua and Julia share one canonical serialiser (`core/ts_fingerprint.py`); each language owns only discovery, target naming and which nodes to drop. Odin tags are **comments**, so they are dropped explicitly rather than incidentally — otherwise `include_docstrings` would let applying a lock change the digest it records.

## Why this proves the code is correct

- **It pins:** that position, whitespace, comments, docstrings and unrelated insertions are all outside the digest, and that applying the tag does not change what the tag records.
- **It would catch:** a fingerprinter that started including position attributes, one that stopped dropping comments, or one that failed to strip the `@locked` tag — any of which would make `cdec lock set` unable to record a stable baseline in the first place.
- **It does not cover:** `include_docstrings: true`, which deliberately *does* make docstring edits significant — see `tests/test_lock_fingerprint.py`.

## How to run and debug

```bash
make test-case CASE=lock/locked/odin/reformat
make debug-case CASE=lock/locked/odin/reformat
```

**Start here:** breakpoint in `tests/case_runner.py::_run_lock`, then step into the engine. Compare `collect_targets(baseline, "odin")` with `collect_targets(src, "odin")` and diff the two digests.

## When to change this case

A red run is a regression until proven otherwise — do not regenerate the baseline to get green. If the requirement genuinely changed, add a new case for the new behaviour and retire this one explicitly. Regenerating (`UPDATE_BASELINES=1 make test-case CASE=lock/locked/odin/reformat`) produces a diff a human reads line by line, in a commit that changes baselines and nothing else.
