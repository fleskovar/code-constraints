# `new-class-constraints` — a new class extends an approved base and sets no metaclass (Python)

## What this proves

`new-class-constraints` checks each **added** class against two independent constraints: an approved base and a forbidden metaclass. The metaclass constraint sits in the `python:` block of the rule entry, and it reads the `metaclass=` keyword of the class statement. This case pins that, plus the indirect base and the exemption of baseline classes.

**Engine:** A — drift — `cdec check`  
**Constraint:** [`new-class-constraints`](../../../../../docs/RULES_CATALOGUE.md#new-class-constraints)  
**Language:** Python  
**Runner:** `tests/case_runner.py::_run_check`

## Inputs

| File | What it is |
| --- | --- |
| `inputs/case.yaml` | Engine and language — the ambient inputs, written down so nothing about the run is implicit |
| `inputs/rules.yaml` | One rule entry: `bases: [Notifier]`, a `python:` block with `forbid_metaclass: ["*"]`, and an `ignore:` glob for test helpers |
| `inputs/src/notifications/base.py` | source under test, identical to the baseline |
| `inputs/src/notifications/sms.py` | source under test |
| `inputs/src/notifications/html.py` | source under test |
| `inputs/src/notifications/retry.py` | source under test |
| `inputs/src/notifications/push.py` | source under test |
| `inputs/src/testing/fake.py` | source under test |
| `inputs/baseline/notifications/base.py` | the agreed baseline — parsed as the OLD side of the diff |

### Why each element is there

| Element | Demonstrates |
| --- | --- |
| `notifications.Notifier` | the approved base. In the baseline, so the rule does not check it |
| `notifications.EmailNotifier` | a baseline class that is the link of the indirect path |
| `notifications.LegacyQueue` | in the baseline with no base. Not `added`, so silent |
| `notifications.SmsNotifier` | `added`, extends `Notifier` directly, no class keyword. Passes |
| `notifications.HtmlEmailNotifier` | `added`, reaches `Notifier` through `EmailNotifier`. Passes |
| `notifications.RetryPolicy` | `added`, no base. **One violation** |
| `notifications.Registry` | `added`, extends `type`, which is not approved. **One violation** |
| `notifications.PushNotifier` | `added`, approved base, but declares `metaclass=Registry`. **One violation** |
| `testing.FakeNotifier` | `added` with no base, but `ignore: [testing.**]` exempts it |

Every element has a line. An element nobody can justify is an element to delete.

## Expected output

`outputs/violations.json` — One row per violation, sorted by `(rule, element, member)`. `element` is the qualified name the violation is attributed to; `member` is the discriminating signature the review key is derived from. Here it names the broken constraint.

```json
[
  {
    "element": "notifications.PushNotifier",
    "member": "forbid_metaclass",
    "rule": "new-class-constraints",
    "severity": "error"
  },
  {
    "element": "notifications.Registry",
    "member": "bases",
    "rule": "new-class-constraints",
    "severity": "error"
  },
  {
    "element": "notifications.RetryPolicy",
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

1. `scope: diff` rules need a baseline. Here `inputs/baseline/` is parsed as the OLD side and `inputs/src/` as the NEW side, and `diff_projects` gives each class a status. Classes are matched by **qualified name**. A Python qualified name is the package (the directory) plus the class name, so the module file is not part of it.
2. The rule checks only the classes whose status is `added`.
3. `ignore:` exempts a qualified name. `testing.**` matches every descendant of `testing`.
4. **`bases`.** The class must derive from a class that matches a glob. The walk starts at the bases the class declares. When a base resolves to a project class, the walk continues with the bases of that class. A glob is matched against the base as written, its short name, and the qualified name of the project class.
5. **`python.forbid_metaclass`.** The `python:` block applies because the project language is Python. The class must not declare a metaclass that matches a glob. The metaclass is the value of the `metaclass=` keyword, so `class C(B, metaclass=Registry)` declares `Registry`. The glob `*` matches each declared metaclass. A class with no `metaclass=` keyword declares none.
6. Each broken constraint is one violation. Its `member` is `bases` or `forbid_metaclass`. The member does not hold the metaclass name, so the key stays the same when the metaclass is renamed.

### Applying them

**Step 1 — diff the two trees (clause 1).**

| Class | In baseline? | In src? | Status |
| --- | --- | --- | --- |
| `notifications.Notifier` | ✅ | ✅ (identical) | `unchanged` |
| `notifications.EmailNotifier` | ✅ | ✅ (identical) | `unchanged` |
| `notifications.LegacyQueue` | ✅ | ✅ (identical) | `unchanged` |
| `notifications.SmsNotifier` | ❌ | ✅ | **`added`** |
| `notifications.HtmlEmailNotifier` | ❌ | ✅ | **`added`** |
| `notifications.RetryPolicy` | ❌ | ✅ | **`added`** |
| `notifications.Registry` | ❌ | ✅ | **`added`** |
| `notifications.PushNotifier` | ❌ | ✅ | **`added`** |
| `testing.FakeNotifier` | ❌ | ✅ | **`added`** |

**Step 2 — keep only `added`, then apply `ignore:` (clauses 2–3).** Six candidates. `testing.FakeNotifier` matches `testing.**`, so five remain.

**Step 3 — check each remaining class (clauses 4–5).**

| Class | Declared bases | Path to `Notifier` | Declared metaclass | `bases` | `forbid_metaclass` |
| --- | --- | --- | --- | --- | --- |
| `SmsNotifier` | `Notifier` | direct | — | ✅ | ✅ |
| `HtmlEmailNotifier` | `EmailNotifier` | `EmailNotifier` → `Notifier` | — | ✅ | ✅ |
| `RetryPolicy` | — | none | — | ❌ | ✅ |
| `Registry` | `type` | none (`type` is not a project class, so the walk stops) | — | ❌ | ✅ |
| `PushNotifier` | `Notifier` | direct | `Registry` | ✅ | ❌ |

**Step 4 — the findings (clause 6).** Each ❌ is one row: three rows on three classes.

### Elements that produce nothing

| Element | Why it is absent from the output |
| --- | --- |
| `notifications.Notifier` | `unchanged`. The rule does not check a baseline class. |
| `notifications.EmailNotifier` | `unchanged`. |
| `notifications.LegacyQueue` | `unchanged`. It has no approved base, but it is not new. |
| `notifications.SmsNotifier` | `added`, and it meets both constraints. |
| `notifications.HtmlEmailNotifier` | `added`, and it meets both constraints through an indirect base. |
| `testing.FakeNotifier` | `added`, but matched by `ignore: [testing.**]`. |

## Why this proves the code is correct

- **It pins:** that the rule keys off `added`, that an indirect base through a project class counts, that the Python parser records the `metaclass=` keyword, and that a base outside the project ends the walk.
- **It would catch:** a regression that checked baseline classes, one that looked only at direct bases, one that lost the class keywords in the parser, or one that keyed the violation on the metaclass name.
- **It does not cover:** `require_metaclass`, `scope: snapshot`, a block of a different language, and a metaclass that a class inherits from its base. The rule reads the declared keyword only. `tests/test_lint_engine.py` asserts the first three.

## How to run and debug

```bash
make test-case CASE=check/new-class-constraints/python
make debug-case CASE=check/new-class-constraints/python
```

**Start here:** breakpoint in `tests/case_runner.py::_run_check`, then step into `lint/rules/new_class_constraints.py::_failures`. Inspect `cls.status`, `cls.bases` and `cls.modifiers`.

## When to change this case

A red run is a regression until proven otherwise — do not regenerate the baseline to get green. If the requirement genuinely changed, add a new case for the new behaviour and retire this one explicitly. Regenerating (`UPDATE_BASELINES=1 make test-case CASE=check/new-class-constraints/python`) produces a diff a human reads line by line, in a commit that changes baselines and nothing else.
