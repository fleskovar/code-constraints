# `frozen-rules` — deleting the tag is the violation (Python)

## What this proves

`frozen-rules` closes the obvious loophole: without it, anyone whose change trips `@immutable` or `@sealed` can delete the tag and go green. Deleting the tag becomes the violation. This case pins all three outcomes — a removed class tag, a **weakened** tag whose parameters changed, and a removed *operation* tag — plus a class outside `classes:` whose identical tag deletion is deliberately not policed.

**Engine:** A — drift — `cdec check`  
**Constraint:** [`frozen-rules`](../../../../../docs/RULES_CATALOGUE.md#frozen-rules)  
**Language:** Python  
**Runner:** `tests/case_runner.py::_run_check`

## Inputs

| File | What it is |
| --- | --- |
| `inputs/case.yaml` | Engine and language — the ambient inputs, written down so nothing about the run is implicit |
| `inputs/rules.yaml` | One rule entry scoped to the `orders` subtree, `scope: diff` |
| `inputs/src/orders/billing.py` | the drifted tags |
| `inputs/src/support/audit.py` | an identical deletion outside `classes:` |
| `inputs/baseline/orders/billing.py` | the agreed baseline — parsed as the OLD side of the diff |
| `inputs/baseline/support/audit.py` | the agreed baseline — parsed as the OLD side of the diff |

### Why each element is there

| Element | Demonstrates |
| --- | --- |
| `orders.Receipt` | `@sealed` deleted; `@immutable` kept. **One violation, not two.** |
| `orders.CheckoutService` | `@no_instantiation(allow=[...])` gained an entry → **`weakened`** |
| `orders.CheckoutService.subtotal` | `@no_side_effects` deleted from an *operation* |
| `support.AuditEntry` | `@sealed` deleted identically — but outside `classes:` |

Every element has a line. An element nobody can justify is an element to delete.

## Expected output

`outputs/violations.json` — One row per violation, sorted by `(rule, element, member)`. `element` is the qualified name the violation is attributed to; `member` is the discriminating signature the review key is derived from.

```json
[
  {
    "element": "orders.CheckoutService",
    "member": "class|@no-instantiation",
    "rule": "freeze-architectural-tags",
    "severity": "error"
  },
  {
    "element": "orders.CheckoutService",
    "member": "operation:subtotal(n:int):float|@no-side-effects",
    "rule": "freeze-architectural-tags",
    "severity": "error"
  },
  {
    "element": "orders.Receipt",
    "member": "class|@sealed",
    "rule": "freeze-architectural-tags",
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
2. This rule reads the tag set from the **baseline** project, not from the diff annotation — the annotated project only carries the *new* tags. That is why `run_checks` threads `baseline_project` through to `ctx.baseline_class_by_qn`.
3. A baseline tag is satisfied only when an **identical** tag — same name, same positional args, same keyword args — still exists on the same element. `RuleAnnotation.__eq__` is what decides.
4. A tag whose name survives but whose parameters differ is reported as `weakened` — **including a tightening**. Changing a constraint's parameters is always a reviewable event.
5. A tag whose name is gone is reported as `removed`.
6. Tags are checked on **classes and on operations**. An operation is matched by signature, and the discriminator is `operation:{signature}|@{tag}` (or `class|@{tag}`).
7. Tag names in the model are **catalog ids**, not the language's spelling: `@no_instantiation` / `[NoInstantiation]` both become `no-instantiation`.

### Applying them

**Step 1 — read the baseline tag set (clause 2).** This is the step that makes the rule
work at all: the *annotated* project carries only the NEW tags, so the engine threads the
baseline project through to `ctx.baseline_class_by_qn`. Tags are stored under their
**catalog id** (clause 6), not the language's spelling — `@no_instantiation` becomes `no-instantiation` and `@no_side_effects` becomes `no-side-effects`.

**Step 2 — for every baseline tag, look for an identical one now (clauses 3–5).**

| Element | Baseline tag | Now | Verdict |
| --- | --- | --- | --- |
| `orders.Receipt` (class) | `sealed` | absent | **`removed`** |
| `orders.Receipt` | `no-instantiation` | present, `allow` list grew | **`weakened`** |
| `orders.Receipt` (class) | `immutable` | present, identical | satisfied |
| `orders.Receipt.subtotal` (operation) | `no-side-effects` | absent | **`removed`** |

**Step 3 — `classes:` bounds the rule.** The `support` package deletes a `sealed` tag in
exactly the same way and is not reported, because it falls outside the `classes:` glob.
That is deliberate: `frozen-rules` is usually adopted subsystem by subsystem.

**Step 4 — the findings.** Each is discriminated by
`class|@{tag}` or `operation:{signature}|@{tag}`, so a class-level and an
operation-level drift on the same class never share a review key.

> Note that **a tightening is also `weakened`**. Any parameter difference is reported,
> because changing a constraint's parameters is always meant to be a reviewable event —
> narrowing an allow-list can break callers just as surely as widening it hides a bug.

### Elements that produce nothing

| Element | Why it is absent from the output |
| --- | --- |
| `the `support` package` | Its `sealed` tag was deleted identically, but `classes:` does not match it. |
| `orders.Receipt / `immutable`` | The tag is still present and identical, so clause 3 is satisfied. |

### Python-specific notes

`@no_side_effects` has **no body analysis at all** — it is captured, visualised and diffed, but nothing verifies the body. `frozen-rules` is what makes it worth writing: once the tag is in the baseline, deleting it fails CI, so the purity claim becomes a reviewable decision rather than a comment someone silently removes.

## Why this proves the code is correct

- **It pins:** that deleting a tag is itself the violation, that a parameter change is `weakened` rather than silently accepted, that operation-level tags are covered as well as class-level ones, and that `classes:` bounds the rule.
- **It would catch:** the loophole this rule exists to close — someone silencing a failing `@immutable` or `@sealed` by deleting the tag. It would also catch a regression that compared only tag *names* (missing the weakening) or that read the current tags instead of the baseline ones.
- **It does not cover:** tag *additions* (never a violation), the `ignore:` option, and the no-baseline skip; see `tests/test_lint_engine.py` and `tests/test_rule_tags.py`.

## How to run and debug

```bash
make test-case CASE=check/frozen-rules/python
make debug-case CASE=check/frozen-rules/python
```

**Start here:** breakpoint in `tests/case_runner.py::_run_check`, then step into the engine. Compare `ctx.baseline_class_by_qn[qn].rules` with `ctx.class_by_qn[qn].rules` — the rule is that diff.

## When to change this case

A red run is a regression until proven otherwise — do not regenerate the baseline to get green. If the requirement genuinely changed, add a new case for the new behaviour and retire this one explicitly. Regenerating (`UPDATE_BASELINES=1 make test-case CASE=check/frozen-rules/python`) produces a diff a human reads line by line, in a commit that changes baselines and nothing else.
