# `subclass-naming` — concrete notifiers must end in `Notifier` (Odin)

## What this proves

`subclass-naming` matches the `base:` glob against the class's **textual** base list and applies `name_pattern:` to the **bare class name** with `fullmatch`. This case pins all four outcomes: a conforming subclass, a violating one, one exempted by `ignore:`, and a class with no matching base that is never examined at all.

**Engine:** A — drift — `cdec check`  
**Constraint:** [`subclass-naming`](../../../../../docs/RULES_CATALOGUE.md#subclass-naming)  
**Language:** Odin  
**Runner:** `tests/case_runner.py::_run_check`

## Inputs

| File | What it is |
| --- | --- |
| `inputs/case.yaml` | Engine and language — the ambient inputs, written down so nothing about the run is implicit |
| `inputs/rules.yaml` | One rule entry: the `base:` glob and the `name_pattern:` regex |
| `inputs/src/notifications/base.odin` | the base plus all three subtypes |
| `inputs/src/orders/order.odin` | a struct with no embedding |

### Why each element is there

| Element | Demonstrates |
| --- | --- |
| `notifications.Notification` | the base struct; embeds nothing |
| `notifications.EmailNotifier` | `using base: Notification` and matches the pattern |
| `notifications.SlackHook` | embeds the base, fails the pattern. **The violation.** |
| `notifications.LegacyPager` | also fails, but is named in `ignore:` |
| `orders.Order` | embeds nothing — never examined |

Every element has a line. An element nobody can justify is an element to delete.

## Expected output

`outputs/violations.json` — One row per violation, sorted by `(rule, element, member)`. `element` is the qualified name the violation is attributed to; `member` is the discriminating signature the review key is derived from.

```json
[
  {
    "element": "notifications.SlackHook",
    "rule": "notifier-implementations-must-end-in-Notifier",
    "severity": "error"
  }
]
```

**Deliberately absent:** messages, file paths and line numbers. A rule's `message:` is prose that gets rewritten, a path is a Windows/POSIX hazard, and a line number moves when someone adds a comment. What the baseline pins is the *identity* of each finding.

## Baseline provenance

**Computed by hand** from the constraint's definition in the catalogue, then checked against the engine. The walkthrough below is the derivation: every row in the baseline appears in it, and no row appears that the walkthrough does not produce.

## Walkthrough

### The rules, stated once

1. `base:` is matched against each entry in the class's base list — **both** the literal base text and its short name — so `IFactory` and `my.pkg.IFactory` both work.
2. `name_pattern:` is applied to the **class name**, not the qualified name, with `fullmatch`.
3. A class with no bases is never matched, whatever it is called.
4. Inheritance is matched **one level at a time** against the declared bases.
5. `ignore:` exempts a class by qualified name.

### Applying them

**Step 1 — for every class, does any base match `base: "Notification"` (clause 1)?**
Then **step 2 — does `fullmatch(".*Notifier$", class_name)` succeed (clause 2)?**

| Class | Bases | Matches `base:`? | Verdict |
| --- | --- | --- | --- |
| `notifications.Notification` | `[]` | ❌ | not examined |
| `notifications.EmailNotifier` | `['Notification']` | ✅ | matches → silent |
| `notifications.SlackHook` | `['Notification']` | ✅ | fails → **Fires** |
| `notifications.LegacyPager` | `['Notification']` | ✅ | `ignore:` exempts it |
| `orders.Order` | `[]` | ❌ | not examined |

**Step 3 — `ignore:` (clause 5)** is applied to the *qualified* name, so the exempted
class is filtered out even though it fails the pattern. That is the difference between
"we accept this one" and "we changed the convention": the entry is visible in
`rules.yaml` and reviewable.

**Step 4 — the finding.** Exactly one class matches the base, fails the pattern, and is
not ignored.

> Note what `fullmatch` buys. The pattern is anchored at *both* ends, so a class called
> `EmailNotifierV2` fails — correctly, since it does not end in `Notifier`. Under
> `re.search` the same pattern would still reject it (`$` anchors the tail), but a
> pattern without a trailing `$` would silently start passing everything. `fullmatch` is
> what makes a loosely-written `name_pattern` fail closed rather than open.

### Elements that produce nothing

| Element | Why it is absent from the output |
| --- | --- |
| `notifications.Notification` | not examined |
| `notifications.EmailNotifier` | matches → silent |
| `notifications.LegacyPager` | `ignore:` exempts it |
| `orders.Order` | not examined |

### Odin-specific notes

Odin has no `class` and no `extends`. Its subtype relation is **struct embedding**: `using base: Notification` splices the base's fields in and makes the struct usable where the base is expected. The parser maps `using base: T` to `bases`, not to an attribute — so a naming convention over an embedding hierarchy is expressible with the ordinary rule, unchanged.

## Why this proves the code is correct

- **It pins:** that the pattern applies to the bare class name, that a class with no matching base is never examined, and that `ignore:` is the per-class escape hatch.
- **It would catch:** a regression that applied the regex to the qualified name (where `.*Notifier$` would still match, but `^Email` would not), one that used `search` instead of `fullmatch`, or one that stopped honouring `ignore:`.
- **It does not cover:** a list-valued `base:`, grandchildren that do not name the base directly, and `scope: diff`; see `tests/test_lint_engine.py`.

## How to run and debug

```bash
make test-case CASE=check/subclass-naming/odin
make debug-case CASE=check/subclass-naming/odin
```

**Start here:** breakpoint in `tests/case_runner.py::_run_check`, then step into the engine. Inspect `cls.bases` for each class — the textual base list is all the rule has to work with.

## When to change this case

A red run is a regression until proven otherwise — do not regenerate the baseline to get green. If the requirement genuinely changed, add a new case for the new behaviour and retire this one explicitly. Regenerating (`UPDATE_BASELINES=1 make test-case CASE=check/subclass-naming/odin`) produces a diff a human reads line by line, in a commit that changes baselines and nothing else.
