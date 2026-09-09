# `no-new-classes` — a new type needs design review first (C#)

## What this proves

`no-new-classes` keys off the diff status `added` **specifically** — not "differs from the baseline". A class that gained a method is `changed`, and stays silent. This case pins that distinction, plus the dotted-descendant behaviour of `ignore:`.

**Engine:** A — drift — `cdec check`  
**Constraint:** [`no-new-classes`](../../../../../docs/RULES_CATALOGUE.md#no-new-classes)  
**Language:** C#  
**Runner:** `tests/case_runner.py::_run_check`

## Inputs

| File | What it is |
| --- | --- |
| `inputs/case.yaml` | Engine and language — the ambient inputs, written down so nothing about the run is implicit |
| `inputs/rules.yaml` | One rule entry at `severity: warning`, `scope: diff`, with an `ignore:` glob for test helpers |
| `inputs/src/Notifications/Base.cs` | source under test |
| `inputs/src/Notifications/Express.cs` | source under test |
| `inputs/src/Testing/Fake.cs` | source under test |
| `inputs/baseline/Notifications/Base.cs` | the agreed baseline — parsed as the OLD side of the diff |

### Why each element is there

| Element | Demonstrates |
| --- | --- |
| `Notifications.ExpressNotifier` | present in `src/`, absent from `baseline/` → status `added`. **The violation.** |
| `Testing.FakeNotifier` | also `added`, but `ignore: [testing.**]` exempts it |
| `Notifications.Notification` | gained a method → status `changed`, not `added`. Silent |
| `Notifications.SmsNotifier` | byte-identical on both sides → status `unchanged`. Silent |

Every element has a line. An element nobody can justify is an element to delete.

## Expected output

`outputs/violations.json` — One row per violation, sorted by `(rule, element, member)`. `element` is the qualified name the violation is attributed to; `member` is the discriminating signature the review key is derived from.

```json
[
  {
    "element": "Notifications.ExpressNotifier",
    "rule": "no-new-classes",
    "severity": "warning"
  }
]
```

**Deliberately absent:** messages, file paths and line numbers. A rule's `message:` is prose that gets rewritten, a path is a Windows/POSIX hazard, and a line number moves when someone adds a comment. What the baseline pins is the *identity* of each finding.

## Baseline provenance

**Computed by hand** from the constraint's definition in the catalogue, then checked against the engine. The walkthrough below is the derivation: every row in the baseline appears in it, and no row appears that the walkthrough does not produce.

## Walkthrough

### The rules, stated once

1. `scope: diff` rules need a baseline. Here `inputs/baseline/` is parsed as the OLD side and `inputs/src/` as the NEW side, and `diff_projects` annotates every element with `added` / `removed` / `changed` / `unchanged`.
2. Classes are matched between the two sides by **qualified name**.
3. The rule fires only for classes whose status is `added` — present in the current model, absent from the baseline.
4. A class that gained or lost a *member* is `changed`, not `added`, so it never fires here. Adding a method is not adding a class.
5. `ignore:` exempts a qualified name. `**` is normalised to `*` and `.` is a normal character, so `testing.**` matches every descendant of `testing`.

### Applying them

**Step 1 — diff the two trees (clause 1).** `inputs/baseline/` is the OLD side,
`inputs/src/` the NEW side; `diff_projects` matches classes by qualified name (clause 2)
and stamps a status on each.

| Class | In baseline? | In src? | Status |
| --- | --- | --- | --- |
| `Notifications.Notification` | ✅ | ✅ (one method added) | `changed` |
| `Notifications.SmsNotifier` | ✅ | ✅ (identical) | `unchanged` |
| `Notifications.ExpressNotifier` | ❌ | ✅ | **`added`** |
| `Testing.FakeNotifier` | ❌ | ✅ | **`added`** |

**Step 2 — keep only `added` (clauses 3–4).** Two candidates. Note that `Notifications.Notification` is
*different* on the two sides and still does not qualify: adding a method is not adding a
class, and a rule that conflated the two would fire on every ordinary change.

**Step 3 — apply `ignore:` (clause 5).** The glob `testing.**` is normalised to
`testing.*`, and `.` is treated as an ordinary character, so it matches `Testing.FakeNotifier`.

**Step 4 — the finding.** One class, at `severity: warning` — on most codebases this
rule is a signal that a design conversation was skipped, not a law.

### Elements that produce nothing

| Element | Why it is absent from the output |
| --- | --- |
| `Notifications.Notification` | `changed`, not `added`. |
| `Notifications.SmsNotifier` | `unchanged`. |
| `Testing.FakeNotifier` | `added`, but matched by `ignore: [testing.**]`. |

## Why this proves the code is correct

- **It pins:** that the rule keys off `added` specifically rather than "differs from baseline", and that `ignore:` globs span dotted descendants.
- **It would catch:** a regression that reported `changed` classes as new, one that lost the `ignore:` glob normalisation so `testing.**` stopped matching, or one that fired without a baseline instead of skipping.
- **It does not cover:** the no-baseline skip path (asserted in `tests/test_lint_engine.py`) and `--base-ref` git baselines.

## How to run and debug

```bash
make test-case CASE=check/no-new-classes/csharp
make debug-case CASE=check/no-new-classes/csharp
```

**Start here:** breakpoint in `tests/case_runner.py::_run_check`, then step into the engine. Inspect `cls.status` on each class of the annotated project.

## When to change this case

A red run is a regression until proven otherwise — do not regenerate the baseline to get green. If the requirement genuinely changed, add a new case for the new behaviour and retire this one explicitly. Regenerating (`UPDATE_BASELINES=1 make test-case CASE=check/no-new-classes/csharp`) produces a diff a human reads line by line, in a commit that changes baselines and nothing else.
