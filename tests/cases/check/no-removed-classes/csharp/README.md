# `no-removed-classes` — a rename is a removal (C#)

## What this proves

`no-removed-classes` fires on a **rename**, because matching is by qualified name and a rename is a removal plus an addition. That is the honest answer — renaming a published type *is* a breaking change for everything importing it — and this case pins it alongside a class whose internals were rewritten without being removed.

**Engine:** A — drift — `cdec check`  
**Constraint:** [`no-removed-classes`](../../../../../docs/RULES_CATALOGUE.md#no-removed-classes)  
**Language:** C#  
**Runner:** `tests/case_runner.py::_run_check`

## Inputs

| File | What it is |
| --- | --- |
| `inputs/case.yaml` | Engine and language — the ambient inputs, written down so nothing about the run is implicit |
| `inputs/rules.yaml` | One rule entry at `severity: error`, `scope: diff` |
| `inputs/src/Notifications/Base.cs` | source under test |
| `inputs/baseline/Notifications/Base.cs` | the agreed baseline — parsed as the OLD side of the diff |

### Why each element is there

| Element | Demonstrates |
| --- | --- |
| `Notifications.SmsNotifier` | in the baseline, gone from `src/` (renamed). **The violation.** |
| `Notifications.TwilioNotifier` | the new name. It is `added` — which this rule does not police |
| `Notifications.EmailNotifier` | kept, with its body rewritten. Not a removal |
| `Notifications.Notification` | untouched |

Every element has a line. An element nobody can justify is an element to delete.

## Expected output

`outputs/violations.json` — One row per violation, sorted by `(rule, element, member)`. `element` is the qualified name the violation is attributed to; `member` is the discriminating signature the review key is derived from.

```json
[
  {
    "element": "Notifications.SmsNotifier",
    "rule": "no-removed-classes",
    "severity": "error"
  }
]
```

**Deliberately absent:** messages, file paths and line numbers. A rule's `message:` is prose that gets rewritten, a path is a Windows/POSIX hazard, and a line number moves when someone adds a comment. What the baseline pins is the *identity* of each finding.

## Baseline provenance

**Computed by hand** from the constraint's definition in the catalogue, then checked against the engine. The walkthrough below is the derivation: every row in the baseline appears in it, and no row appears that the walkthrough does not produce.

## Walkthrough

### The rules, stated once

1. `scope: diff` rules need a baseline. Here `inputs/baseline/` is parsed as the OLD side and `inputs/src/` as the NEW side, and `diff_projects` annotates every element with `added` / `removed` / `changed` / `unchanged`.
2. Classes are matched by **qualified name**. Removed classes are kept in the annotated project with status `removed`, so renderers can show them struck through and rules can see them.
3. The rule fires for every class whose status is `removed`.
4. **A rename is a removal plus an addition.** Matching is by name, so the old name simply stops existing — which is the honest answer, because renaming a published type *is* a breaking change.
5. Rewriting a class's internals leaves its qualified name alone, so it is `unchanged` or `changed`, never `removed`.

### Applying them

**Step 1 — diff the two trees (clauses 1–2).**

| Class | In baseline? | In src? | Status |
| --- | --- | --- | --- |
| `Notifications.Notification` | ✅ | ✅ | `unchanged` |
| `Notifications.SmsNotifier` | ✅ | ❌ | **`removed`** |
| `Notifications.TwilioNotifier` | ❌ | ✅ | `added` |
| `Notifications.EmailNotifier` | ✅ | ✅ (body rewritten, one private helper added) | `changed` |

**Step 2 — the rename (clause 4).** `Notifications.SmsNotifier` and `Notifications.TwilioNotifier` are the *same class* to a
human reader, but matching is by qualified name, so the diff sees one disappear and
another appear. The engine keeps the removed class in the annotated project with status
`removed` precisely so rules can see it — a removed class exists only in the baseline
and has no current source location, which is why the report carries no file or line.

**Step 3 — the rewritten class (clause 5).** `Notifications.EmailNotifier` changed substantially and is
still `changed`, not `removed`: its qualified name never moved.

**Step 4 — the finding.** One class, at `severity: error`. `Notifications.TwilioNotifier` is not reported —
this rule polices removals only; pair it with `no-new-classes` to see both halves of a
rename.

### Elements that produce nothing

| Element | Why it is absent from the output |
| --- | --- |
| `Notifications.TwilioNotifier` | `added`, which is `no-new-classes`' job, not this rule's. |
| `Notifications.EmailNotifier` | `changed` — rewriting internals never removes a class. |
| `Notifications.Notification` | `unchanged`. |

## Why this proves the code is correct

- **It pins:** that a rename reports as a removal, and that rewriting a body is not a removal.
- **It would catch:** a regression that tried to match renamed classes heuristically (and so let a breaking rename through), or one that dropped removed classes from the annotated project so no rule could see them.
- **It does not cover:** the `ignore:` option and the no-baseline skip; see `tests/test_lint_engine.py`.

## How to run and debug

```bash
make test-case CASE=check/no-removed-classes/csharp
make debug-case CASE=check/no-removed-classes/csharp
```

**Start here:** breakpoint in `tests/case_runner.py::_run_check`, then step into the engine. Look for the class with `status == DiffStatus.REMOVED` — it exists only in the annotated project, not in the current source.

## When to change this case

A red run is a regression until proven otherwise — do not regenerate the baseline to get green. If the requirement genuinely changed, add a new case for the new behaviour and retire this one explicitly. Regenerating (`UPDATE_BASELINES=1 make test-case CASE=check/no-removed-classes/csharp`) produces a diff a human reads line by line, in a commit that changes baselines and nothing else.
