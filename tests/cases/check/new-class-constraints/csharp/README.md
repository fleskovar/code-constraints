# `new-class-constraints` — a new class extends an approved base and is `sealed` (C#)

## What this proves

`new-class-constraints` checks each **added** class against two independent constraints: an approved base and a required modifier. The modifier constraint sits in the `csharp:` block of the rule entry. This case pins that a base counts when the class reaches it through another project class, that each broken constraint gives its own row, and that a class of the baseline is exempt.

**Engine:** A — drift — `cdec check`  
**Constraint:** [`new-class-constraints`](../../../../../docs/RULES_CATALOGUE.md#new-class-constraints)  
**Language:** C#  
**Runner:** `tests/case_runner.py::_run_check`

## Inputs

| File | What it is |
| --- | --- |
| `inputs/case.yaml` | Engine and language — the ambient inputs, written down so nothing about the run is implicit |
| `inputs/rules.yaml` | One rule entry: `bases: [Notifier]`, a `csharp:` block with `require_modifiers: [sealed]`, and an `ignore:` glob for test helpers |
| `inputs/src/Notifications/Base.cs` | source under test, identical to the baseline |
| `inputs/src/Notifications/Sms.cs` | source under test |
| `inputs/src/Notifications/Html.cs` | source under test |
| `inputs/src/Notifications/Push.cs` | source under test |
| `inputs/src/Notifications/Retry.cs` | source under test |
| `inputs/src/Notifications/Helpers.cs` | source under test |
| `inputs/src/Testing/Fake.cs` | source under test |
| `inputs/baseline/Notifications/Base.cs` | the agreed baseline — parsed as the OLD side of the diff |

### Why each element is there

| Element | Demonstrates |
| --- | --- |
| `Notifications.Notifier` | the approved base. In the baseline, so the rule does not check it |
| `Notifications.EmailNotifier` | a baseline class that is the link of the indirect path |
| `Notifications.LegacyQueue` | in the baseline with no base and no `sealed`. Not `added`, so silent |
| `Notifications.SmsNotifier` | `added`, extends `Notifier` directly, `sealed`. Passes |
| `Notifications.HtmlEmailNotifier` | `added`, reaches `Notifier` through `EmailNotifier`, `sealed`. Passes |
| `Notifications.PushNotifier` | `added`, approved base, no `sealed`. **One violation** |
| `Notifications.RetryPolicy` | `added`, `sealed`, no base. **One violation** |
| `Notifications.NotifierHelpers` | `added`, `static`, no base and no `sealed`. **Two violations** |
| `Testing.FakeNotifier` | `added` and breaks both constraints, but `ignore: [Testing.**]` exempts it |

Every element has a line. An element nobody can justify is an element to delete.

## Expected output

`outputs/violations.json` — One row per violation, sorted by `(rule, element, member)`. `element` is the qualified name the violation is attributed to; `member` is the discriminating signature the review key is derived from. Here it names the broken constraint.

```json
[
  {
    "element": "Notifications.NotifierHelpers",
    "member": "bases",
    "rule": "new-class-constraints",
    "severity": "error"
  },
  {
    "element": "Notifications.NotifierHelpers",
    "member": "require:sealed",
    "rule": "new-class-constraints",
    "severity": "error"
  },
  {
    "element": "Notifications.PushNotifier",
    "member": "require:sealed",
    "rule": "new-class-constraints",
    "severity": "error"
  },
  {
    "element": "Notifications.RetryPolicy",
    "member": "bases",
    "rule": "new-class-constraints",
    "severity": "error"
  }
]
```

**Deliberately absent:** messages, file paths and line numbers. A rule's `message:` is prose that gets rewritten, a path is a Windows/POSIX hazard, and a line number moves when someone adds a comment. What the baseline pins is the *identity* of each finding.

## Baseline provenance

**Computed by hand** from the constraint's definition in the catalogue, then checked against the engine. The walkthrough below is the derivation: every row in the baseline appears in it, and no row appears that the walkthrough does not produce.

## Walkthrough

### The rules, stated once

1. `scope: diff` rules need a baseline. Here `inputs/baseline/` is parsed as the OLD side and `inputs/src/` as the NEW side, and `diff_projects` gives each class a status. Classes are matched by **qualified name**.
2. The rule checks only the classes whose status is `added`.
3. `ignore:` exempts a qualified name. `Testing.**` matches every descendant of `Testing`.
4. **`bases`.** The class must derive from a class that matches a glob. The walk starts at the bases the class declares. When a base resolves to a project class, the walk continues with the bases of that class. A glob is matched against the base as written, its short name, and the qualified name of the project class.
5. **`csharp.require_modifiers`.** The `csharp:` block applies because the project language is C#. Each glob must match one modifier that the class declares. The C# parser records the modifier keywords in source order, for example `public`, `sealed`.
6. Each broken constraint is one violation. Its `member` is `bases` or `require:<glob>`.

### Applying them

**Step 1 — diff the two trees (clause 1).**

| Class | In baseline? | In src? | Status |
| --- | --- | --- | --- |
| `Notifications.Notifier` | ✅ | ✅ (identical) | `unchanged` |
| `Notifications.EmailNotifier` | ✅ | ✅ (identical) | `unchanged` |
| `Notifications.LegacyQueue` | ✅ | ✅ (identical) | `unchanged` |
| `Notifications.SmsNotifier` | ❌ | ✅ | **`added`** |
| `Notifications.HtmlEmailNotifier` | ❌ | ✅ | **`added`** |
| `Notifications.PushNotifier` | ❌ | ✅ | **`added`** |
| `Notifications.RetryPolicy` | ❌ | ✅ | **`added`** |
| `Notifications.NotifierHelpers` | ❌ | ✅ | **`added`** |
| `Testing.FakeNotifier` | ❌ | ✅ | **`added`** |

**Step 2 — keep only `added`, then apply `ignore:` (clauses 2–3).** Six candidates. `Testing.FakeNotifier` matches `Testing.**`, so five remain.

**Step 3 — check each remaining class (clauses 4–5).**

| Class | Declared bases | Path to `Notifier` | Modifiers | `bases` | `require:sealed` |
| --- | --- | --- | --- | --- | --- |
| `SmsNotifier` | `Notifier` | direct | `public`, `sealed` | ✅ | ✅ |
| `HtmlEmailNotifier` | `EmailNotifier` | `EmailNotifier` → `Notifier` | `public`, `sealed` | ✅ | ✅ |
| `PushNotifier` | `Notifier` | direct | `public` | ✅ | ❌ |
| `RetryPolicy` | — | none | `public`, `sealed` | ❌ | ✅ |
| `NotifierHelpers` | — | none | `public`, `static` | ❌ | ❌ |

**Step 4 — the findings (clause 6).** Each ❌ is one row: four rows on three classes.

### Elements that produce nothing

| Element | Why it is absent from the output |
| --- | --- |
| `Notifications.Notifier` | `unchanged`. The rule does not check a baseline class. |
| `Notifications.EmailNotifier` | `unchanged`. |
| `Notifications.LegacyQueue` | `unchanged`. It breaks both constraints, but it is not new. |
| `Notifications.SmsNotifier` | `added`, and it meets both constraints. |
| `Notifications.HtmlEmailNotifier` | `added`, and it meets both constraints through an indirect base. |
| `Testing.FakeNotifier` | `added`, but matched by `ignore: [Testing.**]`. |

## Why this proves the code is correct

- **It pins:** that the rule keys off `added`, that an indirect base through a project class counts, that the C# parser records `sealed`, and that the two constraints report independently.
- **It would catch:** a regression that checked baseline classes, one that looked only at direct bases, one that lost the class modifiers in the parser, or one that merged two broken constraints into one row.
- **It does not cover:** `forbid_modifiers`, `scope: snapshot`, a block of a different language, and a misplaced option. `tests/test_lint_engine.py` asserts those.

## How to run and debug

```bash
make test-case CASE=check/new-class-constraints/csharp
make debug-case CASE=check/new-class-constraints/csharp
```

**Start here:** breakpoint in `tests/case_runner.py::_run_check`, then step into `lint/rules/new_class_constraints.py::_failures`. Inspect `cls.status`, `cls.bases` and `cls.modifiers`.

## When to change this case

A red run is a regression until proven otherwise — do not regenerate the baseline to get green. If the requirement genuinely changed, add a new case for the new behaviour and retire this one explicitly. Regenerating (`UPDATE_BASELINES=1 make test-case CASE=check/new-class-constraints/csharp`) produces a diff a human reads line by line, in a commit that changes baselines and nothing else.
