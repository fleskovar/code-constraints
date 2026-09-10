# code-constraints Rule & Constraint Catalogue

Every constraint the tool can enforce, in one place. This is the reference a developer
reaches for when writing `.cdec/rules.yaml`, and the menu an architect reads when deciding
which laws are worth encoding.

For the guided, step-by-step introduction see the **[Tutorial](TUTORIAL.md)**; for command
flags and file formats see the **[CLI reference](CLI_REFERENCE.md)**. This document is the
catalogue only — what each constraint means, how to configure it, and what passing and
failing code look like.

---

## Contents

| § | Section | Configured in |
|---|---|---|
| [1](#1--configured-rules-cdecrulesyaml) | **Configured rules** — the `type:` values for `rules.yaml` | `.cdec/rules.yaml` |
| [1.1](#11-structural-drift) | Structural drift — `no-new-classes`, `no-removed-classes`, `frozen-members`, `frozen-rules` | |
| [1.2](#12-dependency--layering) | Dependency & layering — `forbidden-references`, `forbidden-package-references`, `no-cyclic-package-dependencies`, `layer-dependencies` | |
| [1.3](#13-shape--complexity) | Shape & complexity — `dangling-classes`, `subclass-naming`, `max-class-fanout` | |
| [2](#2--source-level-constraint-tags) | **Constraint tags** — decorators/attributes written in the code | source |
| [3](#3--the-reference-gate) | **The reference gate** — `reference-architecture`: freeze the whole public shape | `.cdec/rules.yaml` + `reference.xmi` |
| [4](#4--implementation-locks) | **Implementation locks** — `implementation-locks`: freeze a body byte-for-meaning | `.cdec/rules.yaml` |
| [5](#5--escape-hatches--suppression) | Escape hatches & suppression | |
| [6](#6--choosing-the-right-mechanism) | Choosing the right mechanism | |

---

## The four enforcement mechanisms

Constraints are enforced by four **decoupled** engines. They share the tag *catalogue* and
nothing else — knowing which engine owns a constraint tells you what it can and cannot see.

Every one of them is reached the same way: a `type:` in `.cdec/rules.yaml`, run by
`cdec check`. The engines stay separate underneath; the rule types are thin adapters over
them, so one command gives one report without coupling four different analyses.

| Engine | `type:` | Question it answers | Reads method bodies? | Needs a baseline? | Key |
|---|---|---|---|---|---|
| **A — drift & shape** | the eleven model rules | "Did the architecture drift, and does it obey the laws we wrote down?" | No (model only) | For `scope: diff` rules | `V-` |
| **B — conformance** | `tag-conformance` | "Does the code actually obey its tags right now?" | Yes | No | `F-` |
| **C — freeze** | `implementation-locks` | "Did this specific implementation change at all?" | Yes (digests them) | The `locks:` ledger | `L-` |
| **D — reference gate** | `reference-architecture` | "Did *anything* about the public shape change?" | No (model only) | `reference.xmi` | `R-` |

The key prefix names the engine, not the command, so an exception recorded before the CLI
was unified still resolves.

---

## Master index

| Constraint | Kind | Engine | Section |
|---|---|---|---|
| `no-new-classes` | rules.yaml | A | [1.1](#no-new-classes) |
| `no-removed-classes` | rules.yaml | A | [1.1](#no-removed-classes) |
| `frozen-members` | rules.yaml | A | [1.1](#frozen-members) |
| `frozen-rules` | rules.yaml | A | [1.1](#frozen-rules) |
| `forbidden-references` | rules.yaml | A | [1.2](#forbidden-references) |
| `forbidden-package-references` | rules.yaml | A | [1.2](#forbidden-package-references) |
| `no-cyclic-package-dependencies` | rules.yaml | A | [1.2](#no-cyclic-package-dependencies) |
| `layer-dependencies` | rules.yaml | A (reads `@layer`) | [1.2](#layer-dependencies) |
| `dangling-classes` | rules.yaml | A | [1.3](#dangling-classes) |
| `subclass-naming` | rules.yaml | A | [1.3](#subclass-naming) |
| `max-class-fanout` | rules.yaml | A | [1.3](#max-class-fanout) |
| `@layer` / `[Layer]` | tag | A | [2.1](#layer) |
| `@sealed` / `[Sealed]` | tag | B (structural) | [2.2](#sealed) |
| `@immutable` / `[Immutable]` | tag | B (body) | [2.3](#immutable) |
| `@factory` / `[Factory]` | tag | B (body) | [2.4](#factory) |
| `@no_instantiation` / `[NoInstantiation]` | tag | B (body) | [2.5](#no-instantiation) |
| `@no_side_effects` / `[NoSideEffects]` | tag | drift only | [2.6](#no-side-effects) |
| `@locked` / `[Locked]` | tag | C | [2.7](#locked) |
| `tag-conformance` | rules.yaml | B | [2](#2--source-level-constraint-tags) |
| `reference-architecture` | rules.yaml | D | [3](#3--the-reference-gate) |
| `implementation-locks` | rules.yaml | C | [4](#4--implementation-locks) |
| `targets:` globs | rules.yaml | C | [4](#4--implementation-locks) |

---

## Test coverage — the human-readable case folders

Every constraint below is pinned by at least one **human-readable case folder** under
[`tests/cases/`](../tests/cases/README.md): a real source tree, an expected-findings file,
and a `README.md` whose walkthrough derives the second from the first by hand. Each ✓ links
to that walkthrough — the fastest way to see exactly what a rule does to real code and why.

The matrix is **capability-targeted**, not a full cross-product. The eleven model rules run
on the language-agnostic `Project` model, so their logic is proven once (Python + C#) and the
five other parsers are covered on the rules that actually stress their reference graph —
`forbidden-package-references`, `dangling-classes`, `subclass-naming`, and (for the tag
languages) `layer-dependencies` and `frozen-rules`. The tag engines (B and C) are covered on
every language that has tags; the reference gate (D) on all seven. A `—` therefore means
"this rule's behaviour is proven in another language and this parser is exercised elsewhere",
not "untested".

A case id is its folder path, `engine/constraint/language` — e.g.
`check/subclass-naming/python`. That triple is unique, so single-case constraints need no
further segment; `lock/locked` is the one constraint with several cases per language and
keeps a short variant named after the violation kind it proves
(`changed`, `reformat`, `unlocked`, `missing`, `removed`, `glob`).

Run them with `make test-cases`, one with
`make test-case CASE=<id>`, or under a debugger with `make debug-case CASE=<id>` (or the
"Debug one case folder" VS Code launch configuration). Adding a case is adding a folder —
`tests/test_case_folders.py` discovers them from disk.

| Constraint | Engine | Py | C# | Odin | Lua | Jul | TS | Svelte |
|---|---|---|---|---|---|---|---|---|
| [`no-new-classes`](#no-new-classes) | A | [✓](../tests/cases/check/no-new-classes/python/README.md) | [✓](../tests/cases/check/no-new-classes/csharp/README.md) | — | — | — | — | — |
| [`no-removed-classes`](#no-removed-classes) | A | [✓](../tests/cases/check/no-removed-classes/python/README.md) | [✓](../tests/cases/check/no-removed-classes/csharp/README.md) | — | — | — | — | — |
| [`frozen-members`](#frozen-members) | A | [✓](../tests/cases/check/frozen-members/python/README.md) | [✓](../tests/cases/check/frozen-members/csharp/README.md) | — | — | — | — | — |
| [`frozen-rules`](#frozen-rules) | A | [✓](../tests/cases/check/frozen-rules/python/README.md) | [✓](../tests/cases/check/frozen-rules/csharp/README.md) | [✓](../tests/cases/check/frozen-rules/odin/README.md) | [✓](../tests/cases/check/frozen-rules/lua/README.md) | [✓](../tests/cases/check/frozen-rules/julia/README.md) | — | — |
| [`forbidden-references`](#forbidden-references) | A | [✓](../tests/cases/check/forbidden-references/python/README.md) | [✓](../tests/cases/check/forbidden-references/csharp/README.md) | — | — | — | — | — |
| [`forbidden-package-references`](#forbidden-package-references) | A | [✓](../tests/cases/check/forbidden-package-references/python/README.md) | [✓](../tests/cases/check/forbidden-package-references/csharp/README.md) | [✓](../tests/cases/check/forbidden-package-references/odin/README.md) | [✓](../tests/cases/check/forbidden-package-references/lua/README.md) | [✓](../tests/cases/check/forbidden-package-references/julia/README.md) | [✓](../tests/cases/check/forbidden-package-references/typescript/README.md) | [✓](../tests/cases/check/forbidden-package-references/svelte/README.md) |
| [`no-cyclic-package-dependencies`](#no-cyclic-package-dependencies) | A | [✓](../tests/cases/check/no-cyclic-package-dependencies/python/README.md) | [✓](../tests/cases/check/no-cyclic-package-dependencies/csharp/README.md) | — | — | — | — | — |
| [`layer-dependencies`](#layer-dependencies) | A | [✓](../tests/cases/check/layer-dependencies/python/README.md) | [✓](../tests/cases/check/layer-dependencies/csharp/README.md) | [✓](../tests/cases/check/layer-dependencies/odin/README.md) | [✓](../tests/cases/check/layer-dependencies/lua/README.md) | [✓](../tests/cases/check/layer-dependencies/julia/README.md) | — | — |
| [`dangling-classes`](#dangling-classes) | A | [✓](../tests/cases/check/dangling-classes/python/README.md) | [✓](../tests/cases/check/dangling-classes/csharp/README.md) | [✓](../tests/cases/check/dangling-classes/odin/README.md) | [✓](../tests/cases/check/dangling-classes/lua/README.md) | [✓](../tests/cases/check/dangling-classes/julia/README.md) | [✓](../tests/cases/check/dangling-classes/typescript/README.md) | [✓](../tests/cases/check/dangling-classes/svelte/README.md) |
| [`subclass-naming`](#subclass-naming) | A | [✓](../tests/cases/check/subclass-naming/python/README.md) | [✓](../tests/cases/check/subclass-naming/csharp/README.md) | [✓](../tests/cases/check/subclass-naming/odin/README.md) | [✓](../tests/cases/check/subclass-naming/lua/README.md) | [✓](../tests/cases/check/subclass-naming/julia/README.md) | [✓](../tests/cases/check/subclass-naming/typescript/README.md) | [✓](../tests/cases/check/subclass-naming/svelte/README.md) |
| [`max-class-fanout`](#max-class-fanout) | A | [✓](../tests/cases/check/max-class-fanout/python/README.md) | [✓](../tests/cases/check/max-class-fanout/csharp/README.md) | — | — | — | — | — |
| [`sealed`](#sealed) | B | [✓](../tests/cases/enforce/sealed/python/README.md) | [✓](../tests/cases/enforce/sealed/csharp/README.md) | [✓](../tests/cases/enforce/sealed/odin/README.md) | [✓](../tests/cases/enforce/sealed/lua/README.md) | [✓](../tests/cases/enforce/sealed/julia/README.md) | — | — |
| [`immutable`](#immutable) | B | [✓](../tests/cases/enforce/immutable/python/README.md) | [✓](../tests/cases/enforce/immutable/csharp/README.md) | [✓](../tests/cases/enforce/immutable/odin/README.md) | [✓](../tests/cases/enforce/immutable/lua/README.md) | [✓](../tests/cases/enforce/immutable/julia/README.md) | — | — |
| [`factory`](#factory) | B | [✓](../tests/cases/enforce/factory/python/README.md) | [✓](../tests/cases/enforce/factory/csharp/README.md) | [✓](../tests/cases/enforce/factory/odin/README.md) | [✓](../tests/cases/enforce/factory/lua/README.md) | [✓](../tests/cases/enforce/factory/julia/README.md) | — | — |
| [`no-instantiation`](#no-instantiation) | B | [✓](../tests/cases/enforce/no-instantiation/python/README.md) | [✓](../tests/cases/enforce/no-instantiation/csharp/README.md) | [✓](../tests/cases/enforce/no-instantiation/odin/README.md) | [✓](../tests/cases/enforce/no-instantiation/lua/README.md) | [✓](../tests/cases/enforce/no-instantiation/julia/README.md) | — | — |
| [`locked`](#locked) | C | [✓](../tests/cases/lock/locked/python/changed/README.md) [✓](../tests/cases/lock/locked/python/glob/README.md) [✓](../tests/cases/lock/locked/python/missing/README.md) [✓](../tests/cases/lock/locked/python/reformat/README.md) [✓](../tests/cases/lock/locked/python/removed/README.md) [✓](../tests/cases/lock/locked/python/unlocked/README.md) | [✓](../tests/cases/lock/locked/csharp/changed/README.md) [✓](../tests/cases/lock/locked/csharp/reformat/README.md) [✓](../tests/cases/lock/locked/csharp/unlocked/README.md) | [✓](../tests/cases/lock/locked/odin/changed/README.md) [✓](../tests/cases/lock/locked/odin/reformat/README.md) | [✓](../tests/cases/lock/locked/lua/changed/README.md) [✓](../tests/cases/lock/locked/lua/reformat/README.md) | [✓](../tests/cases/lock/locked/julia/changed/README.md) [✓](../tests/cases/lock/locked/julia/reformat/README.md) | — | — |
| [`reference-gate`](#3--the-reference-gate) | D | [✓](../tests/cases/reference/gate/python/README.md) | [✓](../tests/cases/reference/gate/csharp/README.md) | [✓](../tests/cases/reference/gate/odin/README.md) | [✓](../tests/cases/reference/gate/lua/README.md) | [✓](../tests/cases/reference/gate/julia/README.md) | [✓](../tests/cases/reference/gate/typescript/README.md) | [✓](../tests/cases/reference/gate/svelte/README.md) |

> **Legend.** Engine A = the model rules, B = `tag-conformance`, C = `implementation-locks`,
> D = `reference-architecture`. All four run in `cdec check`. The `locked` row carries
> several cases per language because the five lock *violation kinds* (`changed`, `missing`,
> `removed`, `unlocked`, `algo-mismatch`) and the "reformatting is invisible" guarantee each
> need their own proof.

---

# 1 · Configured rules (`.cdec/rules.yaml`)

## 1.0 Anatomy of a rule entry

Every entry in `rules.yaml` accepts the same six common fields; anything else on the entry
is passed through as a rule-specific option.

```yaml
rules:
  - id: catalog-is-a-leaf-package          # unique, stable — groups the report
    type: forbidden-package-references     # which rule implementation to run
    severity: error                        # error | warning | off
    scope: snapshot                        # diff | snapshot (each type has a default)
    message: |                             # supports {placeholders} + block scalars
      Layering violation: '{source}' must not depend on '{target}'.
    ignore:                                # qualified-name globs exempted from this rule
      - "catalog.legacy.**"
    from: ["catalog"]                      # ← rule-specific options from here down
    to:   ["orders", "users"]
```

| Field | Meaning |
|---|---|
| `id` | Unique and stable. Violations are recorded in the `exceptions:` list under this id, so renaming an id discards its grandfathered suppressions. |
| `type` | The rule implementation. An unknown `type` is a hard config error listing the known ones. |
| `severity` | `error` fails the run at the default `--fail-on error`; `warning` reports without failing; `off` skips the entry entirely (it is never loaded). |
| `scope` | `diff` rules compare against a baseline and are **skipped with a note** — never silently passed — when no baseline is resolvable. `snapshot` rules evaluate the current model alone. |
| `message` | Free text printed when the rule fires, with `{placeholders}` substituted. Each rule's placeholders are listed in its entry below. A malformed placeholder falls back to the raw template rather than crashing. |
| `ignore` | Qualified-name globs. `*` matches anything including dots, and `**` is normalised to `*`, so `orders.**` matches every descendant of `orders`. |

> **YAML gotcha.** YAML 1.1 parses bare `off` as the boolean `false`. The loader coerces it
> back, so `severity: off` works — but quoting it (`severity: "off"`) is clearer.

### What counts as a "reference"

Six of these rules operate on the class-reference graph. A class **A references B** when any
of the following resolve to B:

- an **attribute type** on A (collection wrappers are unwrapped: `List<B>`, `B[]`,
  `dict[str, B]`, `Optional[B]` all resolve to B);
- an **operation parameter or return type** on A;
- a **body-level dependency** recorded by the parser on A;
- a **base class** of A (matched by qualified name, falling back to short name).

Package-level edges are **derived** by aggregating class edges to their containing packages;
there is no separate import graph. Self-references and intra-package edges are dropped.

---

## 1.1 Structural drift

These four answer "did the shape change since we agreed on it?". All default to
`scope: diff` and need a baseline (`.cdec/reference.xmi`, `--reference`, or `--base-ref`).

---

### `no-new-classes`

**Fires when** a class exists in the current model but not in the baseline.

Use it on a frozen subsystem, a generated-code package, or a curated fixture set where every
new type should go through design review first. On most codebases it belongs at
`severity: warning` — it is a *signal*, not a law.

| Option | Type | Default | Meaning |
|---|---|---|---|
| `ignore` | list of globs | `[]` | Qualified names exempt from the rule. |

**Placeholders:** `{qualified_name}`

```yaml
  - id: no-new-classes
    type: no-new-classes
    severity: warning
    scope: diff
    ignore:
      - "tests.**"
      - "**.conftest"
    message: |
      New class '{qualified_name}' appeared. New top-level types in this
      subsystem must be agreed in the design doc first — add it to
      target.json and run `cdec propose` before writing the code.
```

**✅ Passes** — adding a method to a class that already exists in the baseline:

```python
# orders/order.py
class Order:
    def total(self) -> float: ...
    def apply_discount(self, pct: float) -> None:   # new method, not a new class
        ...
```

**❌ Violates** — a new type appears:

```python
# orders/express.py
class ExpressOrder(Order):      # not present in .cdec/reference.xmi
    ...
```

```
[no-new-classes] (warning)
  - orders.ExpressOrder — orders/express.py:1: New class 'orders.ExpressOrder' appeared. New top-level types in this
      subsystem must be agreed in the design doc first — add it to
      target.json and run `cdec propose` before writing the code.

Summary: 0 error(s), 1 warning(s).
```

---

### `no-removed-classes`

**Fires when** a class present in the baseline is gone from the current model. The mirror of
the rule above, and the practical way to protect API stability for downstream consumers.

Note this also fires on a **rename**, because matching is by qualified name — a rename is a
remove plus an add. That is usually what you want: renaming a published type *is* a breaking
change.

| Option | Type | Default | Meaning |
|---|---|---|---|
| `ignore` | list of globs | `[]` | Qualified names exempt from the rule. |

**Placeholders:** `{qualified_name}`

```yaml
  - id: no-removed-classes
    type: no-removed-classes
    severity: error
    scope: diff
    message: |
      Class '{qualified_name}' was removed — a breaking change for anything
      importing it. Deprecate it for one release instead, or, if the removal
      is agreed, run `cdec check --automatic-exceptions reference` in this PR.
```

**✅ Passes** — the class stays, its internals change freely:

```python
class SmsNotifier(Notification):
    def send(self, message: str) -> None:
        self._gateway.publish(message)      # rewritten internals, same class
```

**❌ Violates** — the class is deleted or renamed:

```python
# notifications/sms.py — SmsNotifier renamed to TwilioNotifier
class TwilioNotifier(Notification):
    ...
```

```
[no-removed-classes] (error)
  - notifications.SmsNotifier: Class 'notifications.SmsNotifier' was removed — a breaking change for
      anything importing it. Deprecate it for one release instead, or, if the
      removal is agreed, run `cdec check --automatic-exceptions reference` in this PR.

Summary: 1 error(s), 0 warning(s).
```

(No file/line: a removed class exists only in the baseline, so there is no
current source location to point at.)

---

### `frozen-members`

**Fires when** an attribute or operation on a matched class is **added, removed, or
changed** relative to the baseline. This is how you protect a published contract: an
interface every downstream implementation must satisfy, a DTO other systems deserialise, an
abstract base class.

Members are matched by **signature** (`name:type` for attributes, `name(p:T,q:U):ret` for
operations). A parameter-list change therefore reports as a **removed + added pair**, not a
single "changed" — the old signature disappeared and a new one arrived.

| Option | Type | Default | Meaning |
|---|---|---|---|
| `classes` | list of globs | `["*"]` | Which classes are frozen. |
| `members` | list of globs | `["*"]` | Which members, matched against **either** the bare name or the full signature. |
| `kinds` | list | `[attribute, operation]` | Restrict to one member kind. |
| `ignore` | list of globs | `[]` | Classes exempt from the rule. |

**Placeholders:** `{qualified_name}`, `{member}` (signature), `{kind}`, `{action}` (`added` | `removed` | `changed`)

```yaml
  # Variant A — freeze the whole public API surface.
  - id: freeze-public-api
    type: frozen-members
    severity: error
    scope: diff
    classes: ["myapp.api.**"]
    message: >
      Member '{member}' on '{qualified_name}' was {action}. The public API is
      frozen; bump the major version and update the design doc to change it.

  # Variant B — freeze only the methods of a named contract, letting fields churn.
  - id: lock-notification-abc
    type: frozen-members
    severity: error
    scope: diff
    classes: ["notifications.Notification"]
    kinds: [operation]
    members: ["send*"]
    message: |
      The {kind} '{member}' on '{qualified_name}' was {action}.
      Notification is a public contract — every concrete notifier must keep
      its signature stable. If downstream implementations were updated in
      lockstep, run `cdec check --automatic-exceptions reference` to accept the new baseline.
```

**✅ Passes** — a private helper attribute is added; `kinds: [operation]` does not match it,
and `members: ["send*"]` would not either:

```python
class Notification:
    _retries: int = 3                       # attribute — not covered by kinds
    def send(self, message: str) -> None: ...
```

**❌ Violates** — the contract method gains a parameter:

```python
class Notification:
    def send(self, message: str, urgent: bool) -> None: ...   # was send(message: str)
```

```
[lock-notification-abc] (error)
  - notifications.Notification — notifications/base.py:8: The operation 'send(message:str):None' on 'notifications.Notification' was removed.
      Notification is a public contract — every concrete notifier must keep
      its signature stable. …
  - notifications.Notification — notifications/base.py:8: The operation 'send(message:str,urgent:bool):None' on 'notifications.Notification' was added.
      Notification is a public contract — every concrete notifier must keep
      its signature stable. …

Summary: 2 error(s), 0 warning(s).
```

> **Blind spot.** `frozen-members` will *not* catch a `public` → `private` flip, a
> `static`/`abstract` modifier change, or a class-kind change — the diff engine matches on
> signature and does not compare modifiers. Use the [reference gate](#3--the-reference-gate)
> when you need those covered.

---

### `frozen-rules`

**Fires when** an architectural-rule **tag** recorded in the baseline is removed from, or
changed on, the same element in the current model.

This is the rule that closes the obvious loophole: without it, anyone whose change trips
`@immutable` or `@sealed` can just delete the tag and go green. `frozen-rules` makes
deleting the tag itself the violation.

A tag is satisfied only when an **identical** tag — same name, same positional args, same
keyword args — still exists on the element. Any parameter difference is reported as
`weakened`, including a *tightening*; the intent is that changing a constraint's parameters
is always a reviewable event.

| Option | Type | Default | Meaning |
|---|---|---|---|
| `classes` | list of globs | `["*"]` | Which classes' tags are frozen (covers class-level and operation-level tags). |
| `ignore` | list of globs | `[]` | Classes exempt from the rule. |

**Scope must be `diff`** — it reads the tag set from the baseline model, which the diff
annotation alone does not carry.

**Placeholders:** `{qualified_name}`, `{rule}` (tag name), `{member}` (element the tag sits on), `{action}` (`removed` | `weakened`)

```yaml
  - id: freeze-architectural-tags
    type: frozen-rules
    severity: error
    scope: diff
    classes: ["orders.**"]
    message: |
      Architectural tag drift: '{rule}' on '{member}' of '{qualified_name}'
      was {action}. These tags encode deliberate design constraints
      (factory-only construction, immutability, sealing). Re-add the tag —
      or, if the constraint is genuinely being retired, run
      `cdec check --automatic-exceptions reference` so the decision is reviewable.
```

**✅ Passes** — the tags stay, the implementation changes:

```python
@immutable
@sealed
@layer("orders")
class Receipt:
    def __init__(self, total: float, lines: int) -> None:
        self.total = round(total, 2)      # changed behaviour, tags intact
        self.lines = lines
```

**❌ Violates** — `@sealed` deleted, and `@no_instantiation`'s allow-list edited:

```python
@immutable                                  # @sealed removed
@layer("orders")
class Receipt: ...

@no_instantiation(allow=["AuditEntry", "Receipt"])   # was allow=["AuditEntry"]
class CheckoutService: ...
```

```
[freeze-architectural-tags] (error)
  - orders.Receipt — orders/billing.py:31: Architectural tag drift: 'sealed' on 'orders.Receipt' of
      'orders.Receipt' was removed. These tags encode deliberate design
      constraints (factory-only construction, immutability, sealing). …
  - orders.CheckoutService — orders/billing.py:74: Architectural tag drift: 'no-instantiation' on 'orders.CheckoutService'
      of 'orders.CheckoutService' was weakened. …

Summary: 2 error(s), 0 warning(s).
```

---

## 1.2 Dependency & layering

The rules that keep the dependency graph pointing the way you designed it. All default to
`scope: snapshot` — they evaluate the current model and need no baseline.

---

### `forbidden-references`

**Fires when** a class matching `from` references a class matching `to`.

The precision instrument of the dependency rules: use it when the forbidden edge is between
specific *types* rather than whole packages — "nothing in the domain may touch the concrete
HTTP client", "the catalogue must never learn about customers".

| Option | Type | Default | Meaning |
|---|---|---|---|
| `from` | list of globs | — | Source classes. **Required** — the rule is a no-op if empty. |
| `to` | list of globs | — | Forbidden target classes. **Required.** |
| `ignore` | list of globs | `[]` | Applied to **both** ends: an ignored source or target suppresses the edge. |

Set `scope: diff` to only check classes that were added or changed — useful when
grandfathering a legacy area without a baseline file.

**Placeholders:** `{qualified_name}`, `{source}`, `{target}`

```yaml
  - id: catalog-does-not-reference-customer
    type: forbidden-references
    severity: error
    scope: snapshot
    from: ["catalog.**"]
    to:   ["users.Customer"]
    message: |
      '{source}' references '{target}'. Books and authors must remain ignorant
      of who is buying them — purchase workflows belong in orders/users. If you
      need a customer-specific view of the catalogue, build it in `orders`
      (e.g. a `CustomerCatalogView`) rather than poisoning `catalog`.
```

**✅ Passes** — the catalogue models only catalogue types:

```python
# catalog/book.py
class Book:
    def __init__(self, author: Author, isbn: str) -> None:
        self.author = author
        self.isbn = isbn
```

**❌ Violates** — a customer field, a customer parameter, or a customer base class all count:

```python
# catalog/book.py
from users import Customer

class Book:
    def __init__(self, author: Author, reserved_by: Customer) -> None:   # ← reference
        ...
```

```
[catalog-does-not-reference-customer] (error)
  - catalog.Book — catalog/book.py:4: 'catalog.Book' references 'users.Customer'. Books and authors must remain
      ignorant of who is buying them — purchase workflows belong in
      orders/users. …

Summary: 1 error(s), 0 warning(s).
```

---

### `forbidden-package-references`

**Fires when** any class in a package matching `from` references any class in a package
matching `to`. Package edges are derived by aggregating the class graph, so one forbidden
class edge is enough to fire.

This is the workhorse rule for layering when you do not want to tag every class with
`@layer`. Two or three of these entries express most real layering policies.

| Option | Type | Default | Meaning |
|---|---|---|---|
| `from` | list of globs | — | Source packages. **Required.** |
| `to` | list of globs | — | Forbidden target packages. **Required.** |
| `ignore` | list of globs | `[]` | Applied to both ends (package qualified names). |

Self-edges (`from` package to itself) are always allowed.

**Placeholders:** `{qualified_name}` (= source package), `{source}`, `{target}`

```yaml
  - id: catalog-is-a-leaf-package
    type: forbidden-package-references
    severity: error
    scope: snapshot
    from: ["catalog"]
    to:   ["orders", "users", "notifications"]
    message: |
      Layering violation: '{source}' must not depend on '{target}'.
      `catalog` describes books and authors — pure domain data. It must stay at
      the bottom of the dependency graph so any caller can use it without
      dragging in orders/users/notifications. Move the offending reference to
      whichever package owns the workflow (likely `orders`).
```

**✅ Passes** — the dependency points upward, from `orders` into `catalog`:

```python
# orders/order.py
from catalog import Book

class Order:
    def __init__(self, book: Book) -> None:
        self.book = book
```

**❌ Violates** — the same edge, inverted:

```python
# catalog/book.py
from orders import Order

class Book:
    def __init__(self) -> None:
        self.orders: list[Order] = []
```

```
[catalog-is-a-leaf-package] (error)
  - catalog: Layering violation: 'catalog' must not depend on 'orders'.
      `catalog` describes books and authors — pure domain data. It must stay at
      the bottom of the dependency graph …

Summary: 1 error(s), 0 warning(s).
```

(Package rules report against the package qualified name and carry no file
location — the offending edge may come from any class in the package.)

---

### `no-cyclic-package-dependencies`

**Fires when** the derived package graph contains a cycle. Every elementary cycle is
reported once, attributed to the alphabetically-first package in it, with the full chain in
the message.

Package cycles are the single most reliable predictor of a codebase that cannot be tested,
released, or extracted in pieces. This rule takes no options — it is either on or off — and
is a strong default for any project of more than a handful of packages.

| Option | Type | Default | Meaning |
|---|---|---|---|
| `ignore` | list of globs | `[]` | Matched against the *head* package of the canonicalised cycle. |

**Placeholders:** `{cycle}` — the chain, e.g. `orders -> users -> orders`

```yaml
  - id: no-cyclic-package-dependencies
    type: no-cyclic-package-dependencies
    severity: error
    scope: snapshot
    message: |
      Cyclic package dependency: {cycle}. Package cycles make modules
      impossible to test or ship independently. Resolve by (a) moving the
      shared types into a leaf package both sides can depend on, or
      (b) inverting one direction with an interface — define the protocol in
      the lower package, implement it in the upper one.
```

**✅ Passes** — the cycle is broken by an abstraction owned by the lower package:

```python
# users/customer.py — users defines the protocol it needs
class OrderSummary(Protocol):
    def total(self) -> float: ...

class Customer:
    def __init__(self, latest: OrderSummary) -> None: ...

# orders/order.py — orders implements it; the edge only goes orders → users
class Order:
    def __init__(self, customer: Customer) -> None: ...
    def total(self) -> float: ...
```

**❌ Violates** — both packages name each other's concrete types:

```python
# users/customer.py
from orders import Order
class Customer:
    def __init__(self, latest: Order) -> None: ...

# orders/order.py
from users import Customer
class Order:
    def __init__(self, customer: Customer) -> None: ...
```

```
[no-cyclic-package-dependencies] (error)
  - orders: Cyclic package dependency: orders -> users -> orders. Package cycles make
      modules impossible to test or ship independently. Resolve by (a) moving
      the shared types into a leaf package both sides can depend on, or
      (b) inverting one direction with an interface …

Summary: 1 error(s), 0 warning(s).
```

---

### `layer-dependencies`

**Fires when** a class in layer *A* references a class in layer *B* and *B* is not in *A*'s
allow-list. Layers come from the [`@layer("name")` tag](#layer) in the source, so this rule
is the one place where a `rules.yaml` entry and a source tag work together.

Prefer this over `forbidden-package-references` when your layers do **not** line up with your
directory structure — a common situation in codebases organised by feature rather than by
tier. It expresses the whole policy as one allow-matrix instead of N pairwise prohibitions.

| Option | Type | Default | Meaning |
|---|---|---|---|
| `allow` | mapping `layer -> [layers]` | `{}` | The permitted directions. Empty mapping ⇒ the rule is a no-op. |
| `ignore` | list of globs | `[]` | Applied to both ends (class qualified names). |

Semantics worth internalising:

- **Same-layer references are always allowed**, whatever the matrix says.
- A class whose layer is **not a key** in `allow` is left entirely unconstrained. Add the
  key with an empty list (`domain: []`) to say "this layer may depend on nothing else".
- A reference **to** an untagged class is ignored — the rule can only reason about tagged
  targets. Tag every class in a layered subsystem, or the matrix has holes.

**Placeholders:** `{qualified_name}`, `{source}`, `{target}`, `{source_layer}`, `{target_layer}`

```yaml
  - id: layering
    type: layer-dependencies
    severity: error
    scope: snapshot
    allow:
      presentation:   [application, domain]
      application:    [domain]
      domain:         []                    # depends on nothing
      infrastructure: [domain]
    message: |
      Layering violation: '{source}' ({source_layer}) references '{target}'
      ({target_layer}). Check this rule's `allow:` matrix for what
      {source_layer} may depend on. Usually the fix is to invert the
      dependency: define the interface you need in the lower layer and
      implement it in the higher one.
```

**✅ Passes** — dependency inversion; the domain owns the interface:

```python
from cdec_rules import layer

@layer("domain")
class OrderRepository(Protocol):            # the port lives in the domain
    def save(self, order: "Order") -> None: ...

@layer("infrastructure")
class SqlOrderRepository(OrderRepository):  # infrastructure → domain: allowed
    def save(self, order: "Order") -> None: ...
```

**❌ Violates** — the domain names a concrete infrastructure type:

```python
@layer("infrastructure")
class SqlConnection: ...

@layer("domain")
class Order:
    def __init__(self, conn: SqlConnection) -> None:    # domain → infrastructure
        self.conn = conn
```

```
[layering] (error)
  - domain.Order — domain/order.py:6: Layering violation: 'domain.Order' (domain) references
      'infrastructure.SqlConnection' (infrastructure). Check this rule's
      `allow:` matrix for what domain may depend on. …

Summary: 1 error(s), 0 warning(s).
```

---

## 1.3 Shape & complexity

Rules about the *quality* of the structure rather than its dependencies. Default
`scope: snapshot`; all three also honour `scope: diff`, in which case they only evaluate
classes marked added or changed — the practical way to adopt them on a codebase that would
otherwise light up.

---

### `dangling-classes`

**Fires when** no other class in the project references a class — no attribute type, no
parameter or return type, no body-level usage, no base class. Self-references do not count.

It finds dead code. Its weakness is that it cannot distinguish dead code from a class the
*framework* instantiates — a controller, a DI-registered service, a `main` entry point — so
it needs help. Two options provide it, and a sensible default list of framework base classes
is built in.

| Option | Type | Default | Meaning |
|---|---|---|---|
| `entry_points` | list of globs | `[]` | Exempt classes, matched against **both** the qualified name and the bare class name. |
| `framework_bases` | list of names | `MonoBehaviour`, `ScriptableObject`, `NetworkBehaviour`, `StateMachineBehaviour`, `Editor`, `EditorWindow`, `PropertyDrawer`, `ScriptableWizard` | Base classes whose subclasses are exempt. Inheritance is followed **transitively** through project ancestors. Setting this **replaces** the default list. |
| `ignore` | list of globs | `[]` | Classes exempt from the rule. |

> The check is on **incoming** references only. A class that references plenty of others but
> is referenced by nobody is exactly what this rule is designed to find.

**Placeholders:** `{qualified_name}`

```yaml
  - id: no-dangling-classes
    type: dangling-classes
    severity: warning
    scope: snapshot
    entry_points:
      - "orders.CheckoutService"      # wired by the DI container
      - "*Controller"                 # bare-name glob: every controller
      - "app.main.**"
    framework_bases: ["MonoBehaviour", "BaseCommand"]
    message: |
      Class '{qualified_name}' has no incoming references inside this project.
      If application bootstrap code (a DI container, a `main` entry point)
      wires it up, add its qualified name to this rule's `entry_points:` list.
      Otherwise it is dead code — delete it.
```

**✅ Passes** — referenced by another class, exempted by name, or framework-derived:

```python
class Cart: ...
class CheckoutService:              # listed in entry_points
    def __init__(self, cart: Cart) -> None:    # ← gives Cart an incoming reference
        self.cart = cart

class OrderController(BaseCommand): ...        # framework base → exempt
```

**❌ Violates** — nothing in the project mentions it:

```python
# orders/legacy_pricing.py
class LegacyPriceTable:             # no attribute, parameter, base, or body
    def lookup(self, sku: str) -> float:       # references it anywhere
        ...
```

```
[no-dangling-classes] (warning)
  - orders.LegacyPriceTable — orders/legacy_pricing.py:2: Class 'orders.LegacyPriceTable' has no incoming references inside this
      project. If application bootstrap code (a DI container, a `main`
      entry point) wires it up, add its qualified name to this rule's
      `entry_points:` list. Otherwise it is dead code — delete it.

Summary: 0 error(s), 1 warning(s).
```

---

### `subclass-naming`

**Fires when** a class inherits from a base matching `base` but its own name does not match
the `name_pattern` regex.

Naming conventions are the cheapest form of documentation: `EmailNotifier`, `SmsNotifier`,
`WhatsAppNotifier` tell a reader the role at every call site. This rule is how the convention
survives contact with a new contributor or an agent.

| Option | Type | Default | Meaning |
|---|---|---|---|
| `base` | glob **or list of globs** | — | Matched against each entry in the class's base list — both the literal base text and its short name, so `IFactory` and `myapp.factories.IFactory` both work. **Required.** |
| `name_pattern` | regex | — | Applied to the **class name** (not the qualified name) with `fullmatch`. **Required.** |
| `ignore` | list of globs | `[]` | Classes exempt from the rule. |

Inheritance is matched **one level at a time** against the declared bases; a grandchild whose
parent already satisfies the pattern is only checked if it names the base directly.

**Placeholders:** `{qualified_name}`, `{name}`, `{base}`, `{pattern}`

```yaml
  - id: notifier-implementations-must-end-in-Notifier
    type: subclass-naming
    severity: error
    scope: snapshot
    base: "Notification"
    name_pattern: ".*Notifier$"
    message: |
      Class '{qualified_name}' inherits from `{base}` but its name ({name})
      does not match /{pattern}/. Concrete notifiers must end in `Notifier` so
      the role is obvious at every call site (e.g. `EmailNotifier`,
      `SmsNotifier`). Rename the class, or inherit from a different base.
```

**✅ Passes:**

```python
class EmailNotifier(Notification): ...
class SmsNotifier(Notification): ...
```

**❌ Violates:**

```python
class SlackHook(Notification):      # does not match /.*Notifier$/
    ...
```

```
[notifier-implementations-must-end-in-Notifier] (error)
  - notifications.SlackHook — notifications/slack.py:5: Class 'notifications.SlackHook' inherits from `Notification` but its name
      (SlackHook) does not match /.*Notifier$/. Concrete notifiers must end in
      `Notifier` so the role is obvious at every call site …

Summary: 1 error(s), 0 warning(s).
```

---

### `max-class-fanout`

**Fires when** a class references more than `limit` **distinct** other project classes.

High fanout marks a hub: the class every change ripples through, the one nobody dares
refactor. As a `warning` it is an excellent early-warning metric; as an `error` on a mature
codebase it usually needs a the `exceptions:` list first.

| Option | Type | Default | Meaning |
|---|---|---|---|
| `limit` | int | `10` | Maximum distinct outgoing references. A non-integer value is a hard config error. |
| `ignore` | list of globs | `[]` | Classes exempt — the right home for a deliberate composition root or facade. |

**Placeholders:** `{qualified_name}`, `{fanout}`, `{limit}`

```yaml
  - id: bounded-class-fanout
    type: max-class-fanout
    severity: warning
    scope: snapshot
    limit: 6
    ignore:
      - "app.CompositionRoot"       # wiring everything is its whole job
    message: |
      Class '{qualified_name}' references {fanout} other classes directly
      (limit: {limit}). High fanout signals a hub: every change around it
      ripples outward. Consider splitting responsibilities, introducing a
      facade, or depending on protocols/ABCs instead of concrete types.
```

**✅ Passes** — with `limit: 6`, five distinct references:

```python
class CheckoutService:
    def __init__(self, cart: Cart, receipts: ReceiptFactory,
                 payments: PaymentGateway, audit: AuditLog,
                 notifier: Notification) -> None:      # 5 distinct → under the limit
        ...
```

**❌ Violates** — eight:

```python
class CheckoutService:
    def __init__(self, cart: Cart, receipts: ReceiptFactory,
                 payments: PaymentGateway, audit: AuditLog,
                 notifier: Notification, inventory: Inventory,
                 pricing: PriceTable, shipping: ShippingCalculator) -> None:
        ...
```

```
[bounded-class-fanout] (warning)
  - orders.CheckoutService — orders/checkout.py:1: Class 'orders.CheckoutService' references 8 other classes directly
      (limit: 6). High fanout signals a hub: every change around it ripples
      outward. Consider splitting responsibilities, introducing a facade, or
      depending on protocols/ABCs instead of concrete types.

Summary: 0 error(s), 1 warning(s).
```

---

# 2 · Source-level constraint tags

Tags are **Python decorators**, **C# attributes**, **Julia macros**, or **`@cdec` annotation
comments** (Lua and Odin) that carry a design constraint on the declaration itself. They are
captured on the model, round-trip through XMI, render as badges in the web viewer,
participate in the diff, and are enforced by the `tag-conformance` and
`implementation-locks` rules.

### Installing the shims

The tags are shipped as **no-op** decorators/attributes/macros so tagged code still imports
and compiles with no runtime dependency:

```bash
cdec update-assets       # drops the right shim for your language into the project
```

```python
from cdec_rules import factory, immutable, layer, locked, no_instantiation, no_side_effects, sealed
```

```csharp
using CodeConstraints.Rules;
```

```julia
using CdecRules
```

> **A tag is only recognised when it comes from the shim namespace** — `from cdec_rules
> import …` in Python, `using CodeConstraints.Rules;` in C#, `using CdecRules` in Julia.
> Your own decorator called `sealed` will never be mistaken for the architectural one, and a
> file that forgets the import silently has no tags at all. If a tag is not showing up,
> check the import first.

**Lua and Odin have no import to check**, because they have no construct to hang a no-op on:
Lua has no declaration modifiers at all, and the Odin compiler *rejects unknown `@(...)`
attributes*, so a no-op `@(cdec_sealed)` would not build. Both carry the tag in a namespaced
comment placed where a decorator would go, and the `@cdec` prefix is the namespace:

```lua
---@cdec sealed
---@cdec layer("orders")
local Receipt = {}
```

```odin
//@cdec sealed
//@cdec layer("orders")
Receipt :: struct { total: f64 }
```

Their shims (`cdec_rules.lua`, `cdec_rules.odin`) are still copied into the project as the
in-repo reference for the vocabulary, plus runtime no-ops. ⚠️ **Line adjacency is required** —
a blank line between the comment block and the declaration detaches the tag.

### The tags at a glance

| Tag | Python | C# | Applies to | Enforced by |
|---|---|---|---|---|
| [`layer`](#layer) | `@layer("name")` | `[Layer("name")]` | class | `check` → `layer-dependencies` |
| [`sealed`](#sealed) | `@sealed` | `[Sealed]` | class | `enforce` (structural) |
| [`immutable`](#immutable) | `@immutable` | `[Immutable]` | class | `enforce` (body) |
| [`factory`](#factory) | `@factory(creates=[…])` | `[Factory(Creates = new[]{…})]` | class, method | `enforce` (body) |
| [`no-instantiation`](#no-instantiation) | `@no_instantiation(allow=[…])` | `[NoInstantiation(Allow = new[]{…})]` | class, method | `enforce` (body) |
| [`no-side-effects`](#no-side-effects) | `@no_side_effects` | `[NoSideEffects]` | method | drift only — **body analysis not implemented** |
| [`locked`](#locked) | `@locked(reason=…, owner=…)` | `[Locked(Reason = …, Owner = …)]` | class, method, function | `lock check` |

The same seven tags in the other three languages. One catalogue entry defines every
spelling, so the vocabulary can never drift between languages:

| Tag | Julia | Lua | Odin |
|---|---|---|---|
| `layer` | `@layer "name"` | `---@cdec layer("name")` | `//@cdec layer("name")` |
| `sealed` | `@sealed` | `---@cdec sealed` | `//@cdec sealed` |
| `immutable` | `@immutable` | `---@cdec immutable` | `//@cdec immutable` |
| `factory` | `@factory creates=["R"]` | `---@cdec factory(creates = {"R"})` | `//@cdec factory(creates = ["R"])` |
| `no-instantiation` | `@no_instantiation allow=["A"]` | `---@cdec no_instantiation(allow = {"A"})` | `//@cdec no_instantiation(allow = ["A"])` |
| `no-side-effects` | `@no_side_effects` | `---@cdec no_side_effects` | `//@cdec no_side_effects` |
| `locked` | `@locked reason="…"` | `---@cdec locked(reason = "…")` | `//@cdec locked(reason = "…")` |

⚠️ **Julia arguments are space-separated, not parenthesised.** `@layer "orders"` is correct;
`@layer("orders")` is a Julia *syntax error*. Lua list arguments use table braces (`{"A"}`)
where Odin and Julia use brackets (`["A"]`); both are read correctly.

Tags are available in **Python, C#, Odin, Lua and Julia**. TypeScript and Svelte parse into
the model and support every `rules.yaml` rule, but have no tags, so the `tag-conformance` rule has
nothing to check there and the `implementation-locks` rule refuses by name.

> **Per-language detail** — how each language recovers classes from code that may not have
> them, what `tag-conformance` can and cannot see there, and its parser gotchas — lives in the
> **[per-language guides](languages/README.md)**.

Freeze the *presence* of these tags over time with [`frozen-rules`](#frozen-rules) —
otherwise a failing constraint can be silenced by deleting its tag.

---

### `layer`

**Declares** which architectural layer a class belongs to. Consumed by the
[`layer-dependencies`](#layer-dependencies) rule; on its own the tag enforces nothing.

| Parameter | Type | Meaning |
|---|---|---|
| positional | string | The layer name. Quotes are stripped, so `@layer("domain")` and `[Layer("domain")]` agree. |

```python
from cdec_rules import layer

@layer("domain")
class Order: ...
```

```csharp
using CodeConstraints.Rules;

[Layer("domain")]
public class Order { }
```

**✅ Passes** — with the matrix `application: [domain]`:

```python
@layer("application")
class CheckoutHandler:
    def __init__(self, order: Order) -> None:   # application → domain: allowed
        self.order = order
```

**❌ Violates** — with `domain: []`:

```python
@layer("domain")
class Order:
    def __init__(self, mailer: SmtpMailer) -> None:   # SmtpMailer is @layer("infrastructure")
        self.mailer = mailer
```

```
[layering] (error)
  - domain.Order — domain/order.py:2: layer 'domain' may not depend on layer 'infrastructure' ('domain.Order' -> 'infrastructure.SmtpMailer').

Summary: 1 error(s), 0 warning(s).
```

(That is the built-in message — the text printed when the rule entry has no
`message:` of its own.)

---

### `sealed`

**Fires when** any class in the project subclasses a `@sealed` class. Structural, cross-file,
and evaluated against the parsed model rather than method bodies.

Say it when a type's invariants cannot survive being extended: a value object, a class whose
`__eq__`/`GetHashCode` assumes a closed set of shapes, a type you would rather people compose
than inherit.

Matching is by **short name** — parsers give textual base names, not resolved qualified names
— so a sealed `Receipt` protects against any base spelled `Receipt` or `x.y.Receipt`.

```python
from cdec_rules import sealed

@sealed
class Receipt: ...
```

```csharp
[Sealed]
public class Receipt { }
```

**✅ Passes** — composition instead of inheritance:

```python
@sealed
class Receipt: ...

class AnnotatedReceipt:                 # holds one, does not extend it
    def __init__(self, receipt: Receipt, note: str) -> None:
        self.receipt = receipt
        self.note = note
```

**❌ Violates:**

```python
@sealed
class Receipt: ...

class DiscountedReceipt(Receipt):       # sealed types may not be subclassed
    ...
```

```
[tags-must-be-honoured] (error) — 1 finding(s):
  - [sealed] orders/billing.py:61: 'orders.DiscountedReceipt' subclasses sealed
    class 'Receipt'; sealed types may not be subclassed.
```

---

### `immutable`

**Fires when** a method other than the constructor assigns to one of the class's own fields.

- **Python** — any assignment to `self.<field>` (including `+=` and annotated assignment) in
  a method whose name is not `__init__`.
- **C#** — assignment to `this.<field>` or a bare assignment to a known field name, in any
  method that is not a constructor.

The tag documents a value object; the check keeps it one. Combine with
[`sealed`](#sealed) for the classic immutable-value-type pair.

```python
from cdec_rules import immutable

@immutable
class Receipt:
    def __init__(self, total: float, lines: int) -> None:
        self.total = total          # constructor assignment: fine
        self.lines = lines
```

```csharp
[Immutable]
public class Receipt
{
    public decimal Total { get; }
    public Receipt(decimal total) { Total = total; }
}
```

**✅ Passes** — a "modification" returns a new instance:

```python
@immutable
class Receipt:
    def __init__(self, total: float, lines: int) -> None:
        self.total = total
        self.lines = lines

    def with_discount(self, pct: float) -> "Receipt":
        return Receipt(self.total * (1 - pct), self.lines)   # new object, no mutation
```

**❌ Violates:**

```python
@immutable
class Receipt:
    def __init__(self, total: float, lines: int) -> None:
        self.total = total
        self.lines = lines

    def apply_discount(self, pct: float) -> None:
        self.total *= (1 - pct)          # reassigns a field after construction
```

```
[tags-must-be-honoured] (error) — 1 finding(s):
  - [immutable] orders/billing.py:38: 'orders.Receipt' is @immutable but
    'apply_discount' reassigns field 'self.total' outside __init__.
```

---

### `factory`

**Fires when** a type listed in `creates` is constructed anywhere outside its designated
factory class.

This is how you enforce "there is exactly one way to build this". Useful when construction
carries invariants — validation, registration, ID allocation — that a bare constructor call
would skip.

| Parameter | Type | Meaning |
|---|---|---|
| `creates` | list of **type names** (short names, not qualified) | The types this class/method is the designated constructor for. |

The tag may sit on the **class** or on a **method**; either way the *owning class* becomes
the designated factory, and construction is permitted anywhere inside it.

```python
@factory(creates=["Receipt"])
class ReceiptFactory: ...
```

```csharp
[Factory(Creates = new[] { "Receipt" })]
public class ReceiptFactory { }
```

**✅ Passes** — everyone else goes through the factory:

```python
@factory(creates=["Receipt"])
class ReceiptFactory:
    def for_cart(self, cart: Cart) -> Receipt:
        return Receipt(cart.total(), len(cart.items))    # allowed: this IS the factory

class CheckoutService:
    def __init__(self, receipts: ReceiptFactory) -> None:
        self.receipts = receipts

    def checkout(self, cart: Cart) -> Receipt:
        return self.receipts.for_cart(cart)              # delegates construction
```

**❌ Violates** — a shortcut around the factory:

```python
class CheckoutService:
    def quick_receipt(self, cart: Cart) -> Receipt:
        return Receipt(cart.total(), 1)                  # constructs it directly
```

```
[tags-must-be-honoured] (error) — 1 finding(s):
  - [factory] orders/billing.py:97: 'orders.CheckoutService.quick_receipt'
    constructs 'Receipt' outside its designated factory (ReceiptFactory).
```

---

### `no-instantiation`

**Fires when** the tagged class or method constructs an object whose type is not in `allow`.

The constraint behind "this orchestrator wires collaborators together; it does not build
them". Applied to a class it covers every method; applied to a method it overrides the
class-level setting for that method only.

| Parameter | Type | Meaning |
|---|---|---|
| `allow` | list of type names | Types that may still be constructed. Omit for "nothing at all". |

**Detection differs by language, and this matters:**

- **C# — precise.** Keyed off `object_creation_expression` / `array_creation_expression`
  nodes, so `new Foo()` is unambiguous and nothing else is flagged.
- **Python — heuristic.** There is no type resolution at parse time, so a "construction" is
  *a call whose callee is a known project class, or whose name is Capitalised*. That means
  `Decimal("1.00")`, `Path(p)`, and any Capitalised factory function will be flagged.
  `allow=[…]` is the documented escape hatch and you will need it.

```python
@no_instantiation(allow=["AuditEntry"])
class CheckoutService: ...
```

```csharp
[NoInstantiation(Allow = new[] { "AuditEntry" })]
public class CheckoutService { }
```

**✅ Passes** — collaborators are injected; only the allowed type is built:

```python
@no_instantiation(allow=["AuditEntry", "Decimal"])
class CheckoutService:
    def __init__(self, receipts: ReceiptFactory, audit: AuditLog) -> None:
        self.receipts = receipts
        self.audit = audit

    def checkout(self, cart: Cart) -> Receipt:
        self.audit.record(AuditEntry("checkout"))        # allowed
        return self.receipts.for_cart(cart)              # delegated, not constructed
```

**❌ Violates:**

```python
@no_instantiation(allow=["AuditEntry"])
class CheckoutService:
    def quick_receipt(self, cart: Cart) -> Receipt:
        return Receipt(cart.total(), 1)                  # Receipt is not in allow
```

```
[tags-must-be-honoured] (error) — 1 finding(s):
  - [no-instantiation] orders/billing.py:97: 'orders.CheckoutService.quick_receipt'
    is tagged @no_instantiation but constructs 'Receipt'.
```

> All five tagged demos (`examples/python_demo`, `csharp_demo`, `odin_demo`, `lua_demo`,
> `julia_demo`) ship exactly this seeded violation — it trips both `factory` and `no-instantiation`, producing two
> independent findings from one line. Route the call through the factory and the run goes
> green.

---

### `no-side-effects`

**Declares** an operation free of side effects.

⚠️ **Body analysis is deliberately not implemented.** The tag is captured on the model,
round-trips through XMI, renders as a badge, and participates in the diff — but nothing
verifies the body. Treat it as executable documentation with a drift guarantee, not as a
check.

| Parameter | Type | Meaning |
|---|---|---|
| `allow` | list of names | Reserved for the future body analyzer; captured but unused today. |

What it *does* buy you is [`frozen-rules`](#frozen-rules): once the tag is in the baseline,
removing it fails CI. The purity claim becomes a reviewable decision rather than a comment
someone silently deletes.

```python
from cdec_rules import no_side_effects

class PriceCalculator:
    @no_side_effects
    def subtotal(self, cart: Cart) -> float:
        return sum(line.price for line in cart.items)
```

**✅ Passes** — the tag is present in both the baseline and the current model:

```python
class PriceCalculator:
    @no_side_effects
    def subtotal(self, cart: Cart) -> float:
        return math.fsum(line.price for line in cart.items)   # body changed, tag intact
```

**❌ Violates** — via `frozen-rules`, when the tag is dropped:

```python
class PriceCalculator:
    def subtotal(self, cart: Cart) -> float:        # @no_side_effects removed
        self._last = ...
        return ...
```

```
[freeze-architectural-tags] (error)
  - pricing.PriceCalculator — pricing/calculator.py:4: Architectural tag drift: 'no-side-effects' on 'subtotal(cart:Cart):float'
      of 'pricing.PriceCalculator' was removed. …

Summary: 1 error(s), 0 warning(s).
```

---

### `locked`

**Declares** that an implementation is frozen. The element's normalised AST is digested into
the `locks:` section of `.cdec/rules.yaml` by `cdec check --automatic-exceptions locks`, and `cdec check` fails on any later semantic
change — see [§4](#4--implementation-locks) for the ledger, violation kinds, and the
privilege boundary.

| Parameter | Type | Meaning |
|---|---|---|
| `reason` | string | Why it is frozen. Recorded in the ledger and echoed in violations. |
| `owner` | string | Who to ask for approval. |

Reach for it on code where correctness was hard-won: a settlement calculation finance signed
off on, a security check, a tax rule, a serialisation format other systems parse.

```python
from cdec_rules import locked

class Receipt:
    @locked(reason="receipt wording is contractual; finance signed off on it")
    def formatted(self) -> str:
        return f"{self.lines} line(s) — total {self.total:.2f}"
```

```csharp
[Locked(Reason = "receipt wording is contractual; finance signed off on it")]
public string Formatted() => $"{Lines} line(s) — {Total}";
```

**✅ Passes** — a lock is an **AST identity, not a line range**. Moving the method,
reformatting it, editing comments, and (by default) rewriting docstrings all leave the digest
untouched:

```python
class Receipt:
    """Now with a much better class docstring."""

    def unrelated_new_method(self) -> None:      # inserted ABOVE the locked method
        ...

    @locked(reason="receipt wording is contractual; finance signed off on it")
    def formatted(
        self,
    ) -> str:                                    # reformatted signature
        # a new explanatory comment
        return f"{self.lines} line(s) — total {self.total:.2f}"
```

**❌ Violates** — any semantic change, however small:

```python
    @locked(reason="receipt wording is contractual; finance signed off on it")
    def formatted(self) -> str:
        return f"{self.lines} item(s) — total {self.total:.2f}"   # "line" → "item"
```

```
cdec lock: 1 lock violation(s):
[changed] frozen implementation changed
  - orders.Receipt.formatted — orders/billing.py:43
      'orders.Receipt.formatted' is a frozen method and its implementation changed.
      Lock reason: receipt wording is contractual; finance signed off on it
      Locked by: Fran on 2026-08-02T21:00:38+00:00
      Revert the change, or ask a lead to approve a re-baseline with `cdec check --automatic-exceptions locks --target orders.Receipt.formatted --force`.

A locked implementation may only change with a lead's approval:
  cdec check --automatic-exceptions locks --force
To ship without re-baselining (audited, discouraged):
  cdec check --bypass-locks --bypass-reason "<why>"
```

---

# 3 · The reference gate

`cdec check` is a scalpel — it enforces exactly the rules you listed. `cdec check`
is a wall: **any** structural deviation from the committed `.cdec/reference.xmi` fails, with
no per-rule configuration at all.

```bash
cdec check examples/python_demo --lang python \
     --reference examples/python_demo/.cdec/reference.xmi
```

It runs a **dedicated field-by-field comparator**, not the diff engine, which is why it
catches things `frozen-members` structurally cannot.

### Deviation categories

| Category | Fires when |
|---|---|
| `class-added` | A class exists in the code but not the reference. |
| `class-removed` | A class exists in the reference but not the code. |
| `class-kind-changed` | `class` ⇄ `abstract` ⇄ `interface` ⇄ `enum` ⇄ `struct`. |
| `class-bases-changed` | The base-class list differs. |
| `attribute-added` / `attribute-removed` | An attribute appeared or disappeared. |
| `attribute-changed` | Same attribute, different **type**, **access level**, **static**, **readonly**, or **default value**. |
| `operation-added` / `operation-removed` | A method appeared or disappeared (grouped by name, so overloads are compared as a set). |
| `operation-signature-changed` | The parameter list differs. |
| `operation-return-type-changed` | The return type differs. |
| `operation-modifier-changed` | Same signature, different **access level**, **static**, or **abstract**. |

**✅ Passes** — implementation rewritten, public shape identical:

```python
class Author:
    name: str
    def books(self) -> list[Book]:
        return sorted(self._index.values(), key=lambda b: b.title)   # new internals
```

**❌ Violates** — three changes the reference gate catches that **`cdec check` is
structurally blind to**, even with `frozen-members` enabled, because the diff engine matches
members by signature and never compares modifiers or class kind:

```csharp
public abstract class Book { }              // was a concrete class

public class Author
{
    private List<Book> Books() => …;        // was public
    public static string Format() => …;     // was an instance method
}
```

```
cdec check: 3 deviation(s) from the reference:

  catalog.Author
    - [operation-modifier-changed] Method 'Books' on 'catalog.Author' modifiers changed: access level public -> private.
    - [operation-modifier-changed] Method 'Format' on 'catalog.Author' modifiers changed: static False -> True.

  catalog.Book
    - [class-kind-changed] Class 'catalog.Book' kind changed from class to abstract.
```

A plain added attribute reads the same way:

```
cdec check: 1 deviation(s) from the reference:

  catalog.Author
    - [attribute-added] Property 'test_var:float' was added to 'catalog.Author'.
```

### Accepting a deviation

```
gate fails → reviewer agrees the change is intended
           → author runs `cdec check --automatic-exceptions reference`
           → commits the new reference.xmi in the same PR
           → gate passes
```

| Command | Meaning |
|---|---|
| `cdec check --automatic-exceptions reference` | "Snapshot **what the code is**." — accept a change. |
| `cdec reference set MODEL` | "Declare **what the code should become**." — accept a design. |

> **Directional gotcha.** `cdec reference show` treats the reference as the *target* and your
> code as the current state, so elements present in the reference but missing from the code
> render as **green additions** ("still to build"). That is deliberately the inverse of
> `cdec check` and `diff-vs-xmi`, where the reference is the *old* side.

---

# 4 · Implementation locks

`implementation-locks` answers a narrower question than the rest of the catalogue: not
"did intent drift" or "does the code obey the tag", but **did this body change at all**.

Turn it on with a rule entry, then declare what is frozen — the [`@locked` tag](#locked) in
the source, or `targets:` globs for code you would rather not (or cannot) annotate:

```yaml
# .cdec/rules.yaml
rules:
  - id: frozen-implementations
    type: implementation-locks
    severity: error
    include_docstrings: false     # do docstring edits count as implementation changes?
    targets:
      - "orders.pricing.**"       # freeze an entire module subtree, tag-free
```

Either way the **approved digest** lives in the `locks:` section of the same file, which is
the audit trail and belongs in version control:

```yaml
locks:
- target: orders.Receipt.formatted
  kind: method                  # class | method | function
  algo: py-ast/1                # py-ast/1 (Python) | cs-ts/1 (C#)
  digest: def9d237e48b6d2aae2cc46251c3b670d563130c551bf3116d394a097fe35863
  file: orders/billing.py
  locked_at: '2026-08-02T21:00:38+00:00'
  locked_by: Fran
  reason: receipt wording is contractual; finance signed off on it
```

### Violation kinds

| Kind | Headline | Meaning |
|---|---|---|
| `changed` | frozen implementation changed | The body's digest no longer matches the ledger. |
| `missing` | declared `@locked` but not baselined | Tagged in source but never recorded — run `cdec check --automatic-exceptions locks`. |
| `removed` | frozen element no longer exists | The locked element was deleted or renamed. |
| `unlocked` | `@locked` tag was removed | The tag is gone but the ledger entry remains. **You cannot escape a lock by deleting the tag** — the ledger is the authority. (Glob-locked entries are exempt from this check.) |
| `algo-mismatch` | digest algorithm changed | The ledger predates a fingerprinter change — review and re-baseline. |

### What does and does not trip a lock

| Change | Trips? |
|---|---|
| Reformatting, whitespace, line moves | No |
| Comment edits | No |
| Docstring edits | No, unless `include_docstrings: true` |
| Applying or removing the `@locked` tag itself | No — the tag is stripped recursively before digesting |
| Renaming a **local** variable | Yes |
| Renaming a **parameter**, reordering arguments, changing a literal | Yes |
| Adding an overload / a `@property` setter to a locked name | Yes — same-named siblings are grouped into one target |

### The privilege boundary

```bash
cdec locks --all      # what is lockable and what is locked
cdec check           # the CI gate — exit 1 if anything changed

cdec check --automatic-exceptions locks             # SAFE: only ADDS locks for newly tagged code.
                          # Anyone can run it; it can never erase evidence.

cdec check --automatic-exceptions locks --force
                          # PRIVILEGED: re-baselines a drifted digest, or prunes
                          # an entry whose tag was deleted.
```

Only `--force` re-baselines, and it produces a **reviewable diff on the `locks:` section of `.cdec/rules.yaml`**. Put
that file behind CODEOWNERS and re-baselining becomes a lead-only action that always leaves a
trail:

```
# CODEOWNERS
/.cdec/rules.yaml    @your-org/tech-leads
```

That is the whole design: a junior developer or an agent *can* change locked code — they just
cannot make CI green without a lead approving a visible ledger change.

---

# 5 · Escape hatches & suppression

Every constraint has a deliberate way out. Knowing which one to reach for is most of the
skill of adopting the tool without the team turning it off.

| Hatch | Applies to | Effect | Use when |
|---|---|---|---|
| `severity: warning` | any `rules.yaml` rule | Reported, does not fail | Introducing a rule; tighten later with `--fail-on warning`. |
| `severity: off` | any `rules.yaml` rule | Entry is never loaded | Temporarily parking a rule without deleting its config. |
| `ignore: [globs]` | any `rules.yaml` rule | Named elements exempt | A known, permanent exception — a composition root, generated code, a legacy package. |
| the `exceptions:` section of `.cdec/rules.yaml` | any `rules.yaml` rule | Today's violations grandfathered; **new** ones still fail | Adopting a rule on a codebase that already breaks it. This is the ratchet — write it with `cdec check --automatic-exceptions rules` and let it shrink over time. |
| `entry_points`, `framework_bases` | `dangling-classes` | Class treated as reachable | Framework-instantiated types the model cannot see wired up. |
| `allow=[…]` | `@no_instantiation` | Listed types may be built | Heuristic false positives in Python; genuinely fine constructions (collections, value types). |
| `--base-ref REF` | `scope: diff` rules | Baseline is a live git ref, not `reference.xmi` | PR pipelines — compare against the target branch instead of a committed snapshot. |
| `cdec exceptions allow KEY` | A, B, D | One named issue accepted, with a reason | A specific violation the team agreed is fine. Recorded in `exceptions:`, reviewable in the diff, revocable. |
| `cdec check --automatic-exceptions reference` | A and D | Re-snapshot the agreed architecture | A reviewer approved a deliberate architectural change; commit the new `reference.xmi` in the same pull request. |
| `cdec check --automatic-exceptions locks --force` | C | Re-baseline a frozen implementation | A lead approved a change to locked code. Leaves a reviewable ledger diff. |
| `--bypass-locks` / `CDEC_LOCK_BYPASS` | C | Violations collected but not fatal; audit banner printed; `summary.bypassed` set in JSON | A genuine emergency. Have CI **reject bypassed runs** on protected branches. |
| `--fail-on none` | whole run | Report only, never fail | Week 1 of adoption: collect data before turning anything on. |

Two things are deliberately **not** escape hatches:

- **A missing baseline.** `scope: diff` rules with nothing to compare against are listed
  under "skipped" in the report rather than silently passing. The same is true of any rule
  that cannot run — a `tag-conformance` rule on TypeScript, say.
- **An exception for a lock.** `cdec exceptions allow` refuses an `L-` key, and
  `--automatic-exceptions rules` will not grandfather one. There is exactly one way to
  accept a change to frozen code, and it rewrites the `locks:` section.

---

# 6 · Choosing the right mechanism

### By what you want to say

| You want to say | Reach for |
|---|---|
| "Nothing about the public shape changes without review" | [`reference-architecture`](#3--the-reference-gate) |
| "This package sits at the bottom of the graph" | [`forbidden-package-references`](#forbidden-package-references) |
| "Our layers only depend downward" (layers ≠ directories) | [`@layer`](#layer) + [`layer-dependencies`](#layer-dependencies) |
| "Packages must stay independently shippable" | [`no-cyclic-package-dependencies`](#no-cyclic-package-dependencies) |
| "This interface is a published contract" | [`frozen-members`](#frozen-members) |
| "Nobody quietly deletes a constraint to make their change compile" | [`frozen-rules`](#frozen-rules) |
| "There is one way to construct this type" | [`@factory`](#factory) + [`@no_instantiation`](#no-instantiation) |
| "This is a value object" | [`@immutable`](#immutable) + [`@sealed`](#sealed) |
| "*This function* is settled — nobody touches it" | [`@locked`](#locked) ([§4](#4--implementation-locks)) |
| "Naming tells you the role" | [`subclass-naming`](#subclass-naming) |
| "No class becomes a god object" | [`max-class-fanout`](#max-class-fanout) |
| "Delete the dead code" | [`dangling-classes`](#dangling-classes) |

### By language

| Capability | Python | C# | Odin | Lua | Julia | TypeScript | Svelte |
|---|---|---|---|---|---|---|---|
| Parse to model, diagrams, diff | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Model rules (Engine A) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Constraint tags | ✅ decorators | ✅ attributes | ✅ `//@cdec` | ✅ `---@cdec` | ✅ macros | ❌ | ❌ |
| `tag-conformance` (B) | ✅ heuristic | ✅ precise | ✅ precise | ✅ idiom-based | ✅ name-based | ❌ | ❌ |
| `implementation-locks` (C) | ✅ `py-ast/1` | ✅ `cs-ts/1` | ✅ `odin-ts/1` | ✅ `lua-ts/1` | ✅ `jl-ts/1` | ❌ | ❌ |
| `reference-architecture` (D) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Activity / sequence tags | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |

**"Precise" vs "heuristic"** describes how `tag-conformance` recognises a construction, which is the
only place the languages differ materially in what they can catch:

- **precise** (C#, Odin) — the grammar distinguishes construction outright, so false
  positives are essentially impossible and you rarely need `allow`.
- **heuristic** (Python) — no type resolution, so a call to a Capitalised callee counts;
  `allow=[…]` is the intended escape hatch.
- **name-based** (Julia) — a call counts only when its callee is a type this parse saw. No
  false positives, but constructions of types outside the parse are missed.
- **idiom-based** (Lua) — `T.new(…)` and `setmetatable(t, T)` are recognised; a bare `T(…)`
  is `__call`, not a constructor. Under-reports on unusual constructor conventions.

`implementation-locks` and `tag-conformance` refuse an unsupported language **by name**:
`cdec check` lists the rule as *skipped* with the reason, so "unsupported" and "nothing
tagged" are never confused with "clean".

> **Per-language guides.** Each language has a complete walk-through — how it maps onto the
> UML model, how its tags are spelled, what each engine sees, and its parser gotchas:
> **[Python](languages/PYTHON.md)** · **[C#](languages/CSHARP.md)** ·
> **[Odin](languages/ODIN.md)** · **[Lua](languages/LUA.md)** ·
> **[Julia](languages/JULIA.md)** · **[TypeScript & Svelte](languages/TYPESCRIPT-SVELTE.md)**

### A sane adoption sequence

Turning everything on at once on a mature codebase produces a wall of red and a team that
disables the tool.

1. **Observe** — `cdec check --fail-on none`. Nothing fails; you collect data.
2. **Ratchet** — add rules, run `cdec check --automatic-exceptions rules`, commit the baseline. Existing
   problems are grandfathered; new ones fail.
3. **Tag the crown jewels** — `@sealed` / `@immutable` / `@factory` where the design
   genuinely matters, then add a `tag-conformance` rule. Its `rules:` option lets you adopt
   one tag at a time.
4. **Lock the untouchables** — `@locked` on the handful of bodies that must not change, an
   `implementation-locks` rule, and `.cdec/rules.yaml` behind CODEOWNERS.
5. **Consider `reference-architecture`** — once the architecture is stable enough that
   every structural change *should* be deliberate.

Then work the exceptions down over time. A shrinking `exceptions:` list is a good team
metric, and `cdec exceptions prune` keeps it honest.

### Make the messages teach

The `message:` field is the highest-leverage thing in `rules.yaml`. Compare:

> `forbidden-package-references: catalog -> orders`

with:

> Layering violation: `catalog` must not depend on `orders`. `catalog` describes books and
> authors — pure domain data. It must stay at the bottom of the dependency graph so any
> caller can use it without dragging in orders/users/notifications. Move the offending
> reference to whichever package owns the workflow (likely `orders`).

The second turns a failed build into onboarding — for a person or an agent. The bundled
demo's `rules.yaml` is written this way throughout; copy its style.

---

## Where to go next

- **[Tutorial](TUTORIAL.md)** — the guided path from "I have a codebase" to "CI rejects
  architectural violations".
- **[CLI reference](CLI_REFERENCE.md)** — every command, flag, and config file.
- **[Per-language guides](languages/README.md)** — the same workflow in each language's own
  idiom, with its parser gotchas and a runnable demo.
- **[Examples](../examples/README.md)** — `python_demo`, `csharp_demo`, `odin_demo`,
  `lua_demo` and `julia_demo` each ship a fully-commented `rules.yaml`, tagged classes, a
  committed lock, and one intentional seeded violation.

```bash
make demo      # runs all the engines against both demos
```
