# `@locked` — a semantic change trips the lock (Lua)

## What this proves

The mirror of the reformatting case: **any** semantic edit to a frozen body moves the digest, however small. One character of a string literal is enough. Together the two cases bracket the guarantee — cosmetic in, semantic out.

**Engine:** C — freeze — `cdec lock check`  
**Constraint:** [`locked`](../../../../../../docs/RULES_CATALOGUE.md#locked)  
**Language:** Lua  
**Runner:** `tests/case_runner.py::_run_lock`

## Inputs

| File | What it is |
| --- | --- |
| `inputs/case.yaml` | Engine and language — the ambient inputs, written down so nothing about the run is implicit |
| `inputs/src/billing/invoice.lua` | the same implementation with one semantic edit (an added expression) |
| `inputs/baseline/billing/invoice.lua` | the approved implementation |

### Why each element is there

| Element | Demonstrates |
| --- | --- |
| ``billing.Invoice.formatted`` | the locked method. Exactly one edit: `return self.id` → `return self.id .. "!"` |
| `everything else in the file` | byte-identical, so nothing else can account for the finding |

Every element has a line. An element nobody can justify is an element to delete.

## Expected output

`outputs/lock_violations.json` — One row per lock violation, sorted by `(kind, target)`. An empty list is a meaningful baseline here: it asserts that the edit was invisible to the digest.

```json
[
  {
    "kind": "changed",
    "target": "billing.Invoice.formatted"
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

**Step 0 — build the ledger.** **This case folder contains no sha256.** `inputs/baseline/` is the source as it stood when the lock was approved; the runner digests it to build the ledger, then verifies `inputs/src/` against that. So the "approved digest" is something a reader can see and reason about, and a fingerprinter change shows up as a real diff rather than as a stale opaque hash.

**Step 1 — the edit.** `return self.id` → `return self.id .. "!"` — an added expression. Nothing else in the file differs, which is
what makes this case diagnostic: if it fires, it fired on *this*.

**Step 2 — re-digest (clauses 1–2).** The literal (or the expression) is part of the
normalised tree, so the digest moves.

**Step 3 — the finding (clause 6).** Kind `changed`, target `billing.Invoice.formatted`. The real report
also carries the lock's `reason` and `locked_by`, and prints the escalation path:

```
A locked implementation may only change with a lead's approval:
  cdec lock set --target <name> --force --reason "<why>"
```

That is the whole design. A junior developer or an agent *can* change locked code — they
just cannot make CI green without a lead approving a visible diff on `.cdec/locks.yaml`.
Put that file behind CODEOWNERS and re-baselining always leaves a trail.

**Step 4 — note what is NOT in the baseline.** No digest, no `locked_at`, no `locked_by`.
Those are real but non-deterministic, so pinning them would make the case a clock test.
What is pinned is the *kind* and the *target* — the two things a reviewer acts on.

### Lua-specific notes

A Lua "class" is **not one node** — it is the whole group of statements that build the table — so adding a method to a locked class is a change. And a `---@cdec locked` above a *method* must not be read as locking the class; that is what `_target(..., tag_nodes=)` is for.

## Why this proves the code is correct

- **It pins:** that a one-character semantic edit is detected, and that the violation names the kind and the target.
- **It would catch:** a serialiser that dropped literals (the classic way a digest becomes useless), or a comparison that only checked the element still existed.
- **It does not cover:** `--bypass-locks`, which collects violations without failing and sets `summary.bypassed`; and `algo-mismatch`, which needs a forged ledger and lives in `tests/test_lock_engine.py`.

## How to run and debug

```bash
make test-case CASE=lock/locked/lua/changed
make debug-case CASE=lock/locked/lua/changed
```

**Start here:** breakpoint in `tests/case_runner.py::_run_lock`, then step into the engine. Print both digests — they differ in the first byte, which is all the engine compares.

## When to change this case

A red run is a regression until proven otherwise — do not regenerate the baseline to get green. If the requirement genuinely changed, add a new case for the new behaviour and retire this one explicitly. Regenerating (`UPDATE_BASELINES=1 make test-case CASE=lock/locked/lua/changed`) produces a diff a human reads line by line, in a commit that changes baselines and nothing else.
