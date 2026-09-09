# `frozen-members` — a published contract's signature (C#)

## What this proves

`frozen-members` matches members by **signature**, so a parameter-list change reports as a **removed + added pair** rather than a single "changed". Two findings, two review keys, waivable independently. This is the documented contrast with the reference gate, which matches operations by name and says `operation-signature-changed`.

**Engine:** A — drift — `cdec check`  
**Constraint:** [`frozen-members`](../../../../../docs/RULES_CATALOGUE.md#frozen-members)  
**Language:** C#  
**Runner:** `tests/case_runner.py::_run_check`

## Inputs

| File | What it is |
| --- | --- |
| `inputs/case.yaml` | Engine and language — the ambient inputs, written down so nothing about the run is implicit |
| `inputs/rules.yaml` | One rule entry scoped to a single contract class, restricted to `kinds: [operation]` and `members: ["send*"]` |
| `inputs/src/Notifications/Base.cs` | source under test |
| `inputs/src/Notifications/Sms.cs` | source under test |
| `inputs/baseline/Notifications/Base.cs` | the agreed baseline — parsed as the OLD side of the diff |
| `inputs/baseline/Notifications/Sms.cs` | the agreed baseline — parsed as the OLD side of the diff |

### Why each element is there

| Element | Demonstrates |
| --- | --- |
| `Notifications.Notification.Send` | gained a parameter. **The two violations.** |
| `Notifications.Notification.Describe` | untouched → `unchanged`, so it never reaches the member filter |
| `Notifications.Notification._retries` | a new attribute. `kinds: [operation]` does not cover it |
| `Notifications.SmsNotifier` | changed in exactly the same way, but outside `classes:` — so its churn is invisible to this rule |

Every element has a line. An element nobody can justify is an element to delete.

## Expected output

`outputs/violations.json` — One row per violation, sorted by `(rule, element, member)`. `element` is the qualified name the violation is attributed to; `member` is the discriminating signature the review key is derived from.

```json
[
  {
    "element": "Notifications.Notification",
    "member": "operation:Send(message:string):void",
    "rule": "lock-notification-abc",
    "severity": "error"
  },
  {
    "element": "Notifications.Notification",
    "member": "operation:Send(message:string,urgent:bool):void",
    "rule": "lock-notification-abc",
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
2. Members are matched by **signature**: `name:type` for an attribute, `name(p:T,q:U):ret` for an operation. The receiver (`self` / `this`) is not part of the signature.
3. **A parameter-list change is therefore a removed + added pair, not a single "changed"** — the old signature disappeared and a new one arrived. This is the documented contrast with the reference gate, which matches operations by name and reports `operation-signature-changed`.
4. `classes:` selects which classes are frozen; a class outside it may churn freely.
5. `kinds:` restricts to `attribute` or `operation`; `members:` is matched against **either** the bare name or the full signature.
6. The discriminator is `{kind}:{signature}`, so the two halves of a signature change carry different review keys and can be waived separately.

### Applying them

**Step 1 — select the frozen classes (clause 4).** `classes: [Notifications.Notification]` matches one class.
`Notifications.SmsNotifier` is not matched and is dropped before any member is examined.

**Step 2 — build the member signatures (clause 2).** The receiver (`self` / `this`) is
**not** part of the signature:

| Side | Operation signature |
| --- | --- |
| baseline | `Send(message:string):void` |
| src | `Send(message:string,urgent:bool):void` |

**Step 3 — diff by signature (clause 3).** These are two different strings, so the diff
does not match them to each other. One signature disappeared and a different one
arrived:

| Member | Status |
| --- | --- |
| `Send(message:string):void` | **`removed`** |
| `Send(message:string,urgent:bool):void` | **`added`** |
| `Describe():string` | `unchanged` — filtered out before `members:` is consulted |
| `_retries:int` | `added`, but it is an *attribute* |

**Step 4 — apply `kinds:` and `members:` (clause 5).** `kinds: [operation]` drops the
attribute `_retries:int` outright. `members: ["send*"]` is matched against **either** the
bare name or the full signature, and both surviving members start with the right prefix.

**Step 5 — the findings (clause 6).** Two, discriminated `operation:{signature}`, so
the removal and the addition carry different review keys. A reviewer can waive the
addition while still being told the old signature vanished.

### Elements that produce nothing

| Element | Why it is absent from the output |
| --- | --- |
| `Describe():string` | `unchanged` — the diff only reports members whose status moved. |
| `_retries:int` | `kinds: [operation]` excludes attributes. Without that line this would be a third finding. |
| `Notifications.SmsNotifier` | Outside `classes:`. This row is the point of the option: a contract is frozen, its implementations are free to churn. |

## Why this proves the code is correct

- **It pins:** that members are matched by signature, that a parameter change reports as two violations, and that `classes:` / `kinds:` / `members:` each narrow the rule independently.
- **It would catch:** a regression that started matching operations by name (which would collapse the pair into one finding and silently accept a signature change), one that let `kinds: [operation]` match attributes, or one that included the receiver in the signature.
- **It does not cover:** attribute freezing, the `changed` action (which the diff engine emits only when *rule tags* differ), and glob forms of `classes:`; see `tests/test_lint_engine.py` and `tests/test_diff.py`.

## How to run and debug

```bash
make test-case CASE=check/frozen-members/csharp
make debug-case CASE=check/frozen-members/csharp
```

**Start here:** breakpoint in `tests/case_runner.py::_run_check`, then step into the engine. Inspect `member.status` and `member.signature()` on the frozen class.

## When to change this case

A red run is a regression until proven otherwise — do not regenerate the baseline to get green. If the requirement genuinely changed, add a new case for the new behaviour and retire this one explicitly. Regenerating (`UPDATE_BASELINES=1 make test-case CASE=check/frozen-members/csharp`) produces a diff a human reads line by line, in a commit that changes baselines and nothing else.
