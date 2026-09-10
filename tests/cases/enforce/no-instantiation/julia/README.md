# `@no_instantiation` — an orchestrator wires, it does not build (Julia)

## What this proves

`@no_instantiation(allow=[…])` is the constraint behind "this orchestrator wires collaborators together; it does not build them". This case pins that the allow-list is consulted by **short type name**, and that everything not on it fires.

**Engine:** B — conformance — the `tag-conformance` rule  
**Constraint:** [`no-instantiation`](../../../../../docs/RULES_CATALOGUE.md#no-instantiation)  
**Language:** Julia  
**Runner:** `tests/case_runner.py::_run_enforce`

## Inputs

| File | What it is |
| --- | --- |
| `inputs/case.yaml` | Engine and language — the ambient inputs, written down so nothing about the run is implicit |
| `inputs/src/orders/Orders.jl` | source under test |

### Why each element is there

| Element | Demonstrates |
| --- | --- |
| `orders.Orders.CheckoutService` | carries `allow=["AuditEntry"]` at class level, so clause 3 covers every method below |
| `orders.Orders.CheckoutService.checkout` | builds `AuditEntry("checkout")` — on the allow-list, so silent |
| `orders.Orders.CheckoutService.quick_receipt` | builds `Receipt(total)` — not on the list. **The violation.** |

Every element has a line. An element nobody can justify is an element to delete.

## Expected output

`outputs/findings.json` — One row per finding, sorted by `(rule, element, detail)`. `element` is the class the finding is attributed to; `detail` is the stable discriminator (`method->Type` for a construction, `method.field` for a reassignment) that lets two findings of one rule on one class carry different review keys.

```json
[
  {
    "detail": "quick_receipt->Receipt",
    "element": "orders.Orders.CheckoutService",
    "rule": "no-instantiation"
  }
]
```

**Deliberately absent:** messages, file paths and line numbers. A rule's `message:` is prose that gets rewritten, a path is a Windows/POSIX hazard, and a line number moves when someone adds a comment. What the baseline pins is the *identity* of each finding.

## Baseline provenance

**Computed by hand** from the constraint's definition in the catalogue, then checked against the engine. The walkthrough below is the derivation: every row in the baseline appears in it, and no row appears that the walkthrough does not produce.

## Walkthrough

### The rules, stated once

1. The `tag-conformance` rule **re-parses the source and reads method bodies**. It never consults the reference model or the diff, so it needs no baseline: the question is not "did intent drift" but "does this code obey its tags right now".
2. Construction detection in this language is **name-based**. Construction has no dedicated syntax: `Money(1.0)` is an ordinary call, indistinguishable at the grammar level from `round(1.0)`. So a call counts only when its callee names a type *this parse saw*. Narrower than Python's heuristic — no false positives on stdlib calls — at the cost of missing constructions of types outside the parse.
3. Applied to a **class** the tag covers every method in it. Applied to a method it overrides the class-level setting for that method only.
4. `allow:` holds **short type names**. A construction whose type is on the list is permitted; omit `allow` entirely for "nothing at all".
5. The finding is attributed to the tagged class, with the discriminator `{method}->{Type}`.
6. **A type may always construct itself.** Without that rule every `T.new` / inner constructor would be flagged, and the idiom would be unusable.

### Applying them

**Step 1 — find the tagged class and read its allow-list (clauses 3–4).**
`orders.Orders.CheckoutService` → `allow = {AuditEntry}`.

**Step 2 — find every construction inside it (clause 2).**

| Method | Constructs | On the allow-list? | Verdict |
| --- | --- | --- | --- |
| `checkout` | `AuditEntry("checkout")` → `AuditEntry` | ✅ | silent |
| `quick_receipt` | `Receipt(total)` → `Receipt` | ❌ | **Fires** |

**Step 3 — the finding (clause 5).** Attributed to `orders.Orders.CheckoutService`, discriminated
`quick_receipt->Receipt`.

The `checkout` row is not decoration: it proves the allow-list is actually consulted
rather than the rule simply firing on everything. Delete `AuditEntry` from `allow` and
this case grows a second finding — which is the quickest way to convince yourself the
mechanism works.

### Elements that produce nothing

| Element | Why it is absent from the output |
| --- | --- |
| `orders.Orders.CheckoutService.checkout` | `AuditEntry` is named in `allow:`. The one collaborator this orchestrator is trusted to build. |

## Why this proves the code is correct

- **It pins:** that the tag covers every method of the class it sits on, that `allow:` is matched by short type name, and that the discriminator names the method and the constructed type.
- **It would catch:** a regression that ignored `allow:` (which would make the tag unusable in Python, where the heuristic over-reports), one that only checked the constructor, or one that stopped covering methods inherited into the class's own body.
- **It does not cover:** the method-level form of the tag, which overrides the class-level setting for one method only, and the empty `allow` case meaning "nothing at all".

## How to run and debug

```bash
make test-case CASE=enforce/no-instantiation/julia
make debug-case CASE=enforce/no-instantiation/julia
```

**Start here:** breakpoint in `tests/case_runner.py::_run_enforce`, then step into the engine. Watch `literal_set` parse the `allow=` value — it reads `["A"]` and `{"A"}` alike, so one reader serves every language.

## When to change this case

A red run is a regression until proven otherwise — do not regenerate the baseline to get green. If the requirement genuinely changed, add a new case for the new behaviour and retire this one explicitly. Regenerating (`UPDATE_BASELINES=1 make test-case CASE=enforce/no-instantiation/julia`) produces a diff a human reads line by line, in a commit that changes baselines and nothing else.
