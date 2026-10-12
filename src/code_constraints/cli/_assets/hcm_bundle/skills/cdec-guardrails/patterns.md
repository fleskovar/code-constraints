# Pattern cookbook

Each recipe gives the decision, the tags, the rule entries and what fails afterwards. The
code examples are in Python. The tag for each other language is in `./tags.md`. The
options of each rule type are in `./rules.md`.

| # | Pattern | Mechanism |
| --- | --- | --- |
| 1 | [Layers that are the folders](#1-layers-that-are-the-folders) | `forbidden-package-references` |
| 2 | [Layers that are not the folders](#2-layers-that-are-not-the-folders) | `layer` + `layer-dependencies` |
| 3 | [Ports and adapters](#3-ports-and-adapters) | `layer` + `layer-dependencies` + `subclass-naming` |
| 4 | [Model, view, controller](#4-model-view-controller) | `forbidden-package-references` |
| 5 | [Independent modules](#5-independent-modules) | `no-cyclic-package-dependencies` |
| 6 | [Factory](#6-factory) | `factory` + `no-instantiation` |
| 7 | [Value object](#7-value-object) | `immutable` + `sealed` |
| 8 | [Service that wires and does not build](#8-service-that-wires-and-does-not-build) | `no-instantiation` |
| 9 | [Strategy or plugin family](#9-strategy-or-plugin-family) | `subclass-naming` + `frozen-members` |
| 10 | [Published contract](#10-published-contract) | `frozen-members` + `no-removed-classes` |
| 11 | [Frozen subsystem](#11-frozen-subsystem) | `no-new-classes` + `reference-architecture` |
| 12 | [Settled implementation](#12-settled-implementation) | `locked` + `implementation-locks` |
| 13 | [Complexity budget](#13-complexity-budget) | `max-class-fanout` + `dangling-classes` |
| 14 | [Guardrails that stay](#14-guardrails-that-stay) | `frozen-rules` |
| 15 | [A fast set and a full set](#15-a-fast-set-and-a-full-set) | `.cdec/rules/*.yaml` |
| 16 | [Closed set of building blocks](#16-closed-set-of-building-blocks) | `new-class-constraints` |

---

## 1. Layers that are the folders

**Decision:** "The domain depends on nothing. The UI depends on the domain. Nothing
depends on the UI."

Use this recipe when each layer is one package. It needs no tags, so it also works for
TypeScript and Svelte. Write one entry for each layer that has a forbidden direction.

```yaml
  - id: domain-depends-on-nothing
    type: forbidden-package-references
    severity: error
    from: ["shop.domain.**"]
    to:   ["shop.application.**", "shop.infrastructure.**", "shop.ui.**"]
    message: |
      Layering violation: '{source}' must not depend on '{target}'. The domain is
      pure business rules. Define the interface that you need in the domain, and
      implement it in the outer layer.

  - id: application-does-not-depend-on-ui
    type: forbidden-package-references
    severity: error
    from: ["shop.application.**"]
    to:   ["shop.ui.**"]
```

The glob `shop.ui.**` matches the package `shop.ui` and each of its sub-packages.

**Fails:** a class in `shop.domain` with an attribute, a parameter, a return type or a
base class from `shop.infrastructure`.

## 2. Layers that are not the folders

**Decision:** the same as recipe 1, but the code is organised by feature. Each feature
folder has classes of more than one layer.

Tag each class with its layer. Then write the full policy as one matrix.

```python
from cdec_rules import layer

@layer("domain")
class Order: ...

@layer("application")
class PlaceOrder:
    def __init__(self, orders: "OrderRepository") -> None: ...
```

```yaml
  - id: layering
    type: layer-dependencies
    severity: error
    allow:
      presentation:   [application, domain]
      application:    [domain]
      domain:         []                # the domain depends on nothing
      infrastructure: [domain, application]
    message: |
      Layering violation: '{source}' ({source_layer}) references '{target}'
      ({target_layer}). See the `allow:` matrix of this rule.
```

**Fails:** a `domain` class that refers to an `infrastructure` class.

**Traps:** a class with no `layer` tag is invisible to this rule. Tag each class of the
subsystem. Write `domain: []` explicitly. A layer that is not a key has no constraint.

## 3. Ports and adapters

**Decision:** "The domain owns the interfaces (ports). The infrastructure implements them
(adapters). The domain does not name a concrete adapter."

```python
from typing import Protocol
from cdec_rules import layer

@layer("domain")
class OrderRepository(Protocol):                 # the port
    def save(self, order: "Order") -> None: ...

@layer("infrastructure")
class SqlOrderRepository(OrderRepository):       # the adapter
    def save(self, order: "Order") -> None: ...
```

```yaml
  - id: layering
    type: layer-dependencies
    severity: error
    allow:
      domain:         []
      application:    [domain]
      infrastructure: [domain]          # adapters see the ports, not the use cases

  - id: adapters-name-their-port
    type: subclass-naming
    severity: error
    base: "*Repository"
    name_pattern: ".*Repository$"
    message: |
      Class '{qualified_name}' implements `{base}`, but its name ({name}) does not
      match /{pattern}/. Name an adapter after its port, for example
      `SqlOrderRepository`.

  - id: ports-are-stable
    type: frozen-members
    severity: error
    scope: diff
    classes: ["shop.domain.*Repository"]
    kinds: [operation]
    message: |
      The {kind} '{member}' on port '{qualified_name}' was {action}. Each adapter
      implements this port. Change the port and its adapters as one design change.
```

**Fails:** a domain class that takes a `SqlOrderRepository`, an adapter with the name
`OrderSql`, and a changed method on a port.

## 4. Model, view, controller

**Decision:** "The model does not know the view or the controller. The view does not know
the controller."

```yaml
  - id: model-is-independent
    type: forbidden-package-references
    severity: error
    from: ["app.models.**"]
    to:   ["app.views.**", "app.controllers.**"]
    message: |
      '{source}' must not depend on '{target}'. The model is the state and the
      rules. Send a change to the view through an event or through the controller.

  - id: view-does-not-call-controller
    type: forbidden-package-references
    severity: error
    from: ["app.views.**"]
    to:   ["app.controllers.**"]

  - id: controllers-are-named-controllers
    type: subclass-naming
    severity: error
    base: "Controller"
    name_pattern: ".*Controller$"
```

## 5. Independent modules

**Decision:** "Each package can be tested and released alone."

```yaml
  - id: no-cyclic-package-dependencies
    type: no-cyclic-package-dependencies
    severity: error
    message: |
      Cyclic package dependency: {cycle}. Move the shared types to a leaf package,
      or invert one direction with an interface that the lower package owns.
```

To make one package a leaf, add recipe 1 with that package in `from`.

**Fails:** `orders` refers to `users`, and `users` refers to `orders`.

## 6. Factory

**Decision:** "Only `ReceiptFactory` constructs a `Receipt`."

Use this when construction has rules that a direct constructor call skips, such as
validation, registration or the allocation of an id.

```python
from cdec_rules import factory, no_instantiation

@factory(creates=["Receipt"])
class ReceiptFactory:
    def for_cart(self, cart: Cart) -> Receipt:
        return Receipt(cart.total(), len(cart.items))

@no_instantiation(allow=["AuditEntry"])
class CheckoutService:
    def __init__(self, receipts: ReceiptFactory) -> None:
        self.receipts = receipts

    def checkout(self, cart: Cart) -> Receipt:
        return self.receipts.for_cart(cart)
```

```yaml
  - id: tags-must-be-honoured
    type: tag-conformance
    severity: error
    message: |
      [{rule}] {message}
      Get the object from its factory. Do not construct it directly.
```

**Fails:** `Receipt(...)` in a class that is not `ReceiptFactory`.

**Variants:** for a builder, put `@factory(creates=["Report"])` on the builder class. For
an abstract factory, put the tag on each concrete factory with its own `creates` list.

## 7. Value object

**Decision:** "A `Money` has no identity and does not change. Nobody extends it."

```python
from cdec_rules import immutable, sealed

@immutable
@sealed
class Money:
    def __init__(self, amount: int, currency: str) -> None:
        self.amount = amount
        self.currency = currency

    def plus(self, other: "Money") -> "Money":
        return Money(self.amount + other.amount, self.currency)
```

The rule is the `tag-conformance` entry of recipe 6. To adopt only these two tags, add
`rules: [immutable, sealed]` to that entry.

**Fails:** a method that assigns `self.amount`, and a class that extends `Money`.

## 8. Service that wires and does not build

**Decision:** "A use case gets its collaborators through its constructor. It does not
construct them." This is dependency injection as a check.

```python
from cdec_rules import no_instantiation

@no_instantiation(allow=["OrderPlaced"])        # it can build its own events
class PlaceOrder:
    def __init__(self, orders: OrderRepository, clock: Clock) -> None:
        self.orders = orders
        self.clock = clock
```

Add the `tag-conformance` entry of recipe 6.

**Fails:** `SqlOrderRepository()` in a method of `PlaceOrder`.

**Trap:** in Python, each capitalised call counts as a construction. Put standard value
types such as `Decimal` and `Path` in `allow`.

## 9. Strategy or plugin family

**Decision:** "Each pricing rule extends `PricingStrategy`. Its name ends in `Strategy`.
The interface is stable."

```yaml
  - id: strategies-are-named-strategies
    type: subclass-naming
    severity: error
    base: "PricingStrategy"
    name_pattern: ".*Strategy$"
    message: |
      Class '{qualified_name}' inherits from `{base}`, but its name ({name}) does
      not match /{pattern}/. The name tells the role at each call site.

  - id: strategy-interface-is-frozen
    type: frozen-members
    severity: error
    scope: diff
    classes: ["pricing.PricingStrategy"]
    kinds: [operation]

  - id: context-does-not-name-a-concrete-strategy
    type: forbidden-references
    severity: error
    from: ["pricing.PriceCalculator"]
    to:   ["pricing.*Strategy"]
    ignore: ["pricing.PricingStrategy"]
    message: |
      '{source}' references the concrete strategy '{target}'. Depend on
      `PricingStrategy`, and let the caller select the implementation.
```

The same recipe works for a family of commands, handlers, notifiers or observers. Change
the base name and the pattern.

This recipe controls the classes that join the family. To make each new class join a
family, add recipe 16.

## 10. Published contract

**Decision:** "Other systems use `api.*`. Its classes and its methods do not disappear or
change without a major version."

```yaml
  - id: public-api-members-are-frozen
    type: frozen-members
    severity: error
    scope: diff
    classes: ["shop.api.**"]
    message: |
      Member '{member}' on '{qualified_name}' was {action}. The public API is
      frozen. Get the change approved as a design change, with a version increase.

  - id: public-api-classes-stay
    type: no-removed-classes
    severity: error
    scope: diff
    ignore: ["shop.internal.**"]
```

`frozen-members` does not see a change from `public` to `private`. If that matters, add
`reference-architecture` with `categories: [operation-modifier-changed, attribute-changed]`.

## 11. Frozen subsystem

**Decision:** "Each structural change in this subsystem is deliberate and reviewed."

```yaml
  - id: public-shape-is-frozen
    type: reference-architecture
    severity: error

  - id: no-new-classes-in-core
    type: no-new-classes
    severity: error
    scope: diff
    ignore: ["tests.**"]
    message: |
      New class '{qualified_name}' appeared. Agree each new type first: add it to
      the model, run `cdec propose`, and get the approval.
```

With `reference-architecture`, the approved model is the only way to change the shape.
This is the rule that makes the architecture-first workflow binding.

**Softer variant:** list only some categories, for example
`categories: [class-removed, operation-removed, operation-signature-changed]`. Then new
classes and new members pass, and removed or changed ones fail.

To permit a new class that extends an approved base, use recipe 16 in place of
`no-new-classes`.

## 12. Settled implementation

**Decision:** "This calculation is correct and approved. Nobody changes its body."

```python
from cdec_rules import locked

class Invoice:
    @locked(reason="settlement order agreed with finance", owner="finance-leads")
    def settle(self, amount: float) -> float:
        tax = amount * 0.2
        return amount + tax
```

```yaml
  - id: frozen-implementations
    type: implementation-locks
    severity: error
    targets:
      - "tests.acceptance.**"      # freeze the acceptance tests without tags
```

Then a person approves `cdec check --automatic-exceptions locks`, which records the
digests. Put `.cdec/rules.yaml` behind CODEOWNERS, so that only a lead can accept a change.
A lead accepts one approved change with
`cdec check --automatic-exceptions locks --target Invoice.settle --force`.

**Fails:** a changed literal, a renamed local variable, a new statement, a removed tag.
**Passes:** moved code, a new format, an edited comment.

Use `targets` to freeze test code. Then an agent cannot change a test to make it pass.

## 13. Complexity budget

**Decision:** "No class becomes a hub. Dead classes are deleted."

```yaml
  - id: bounded-class-fanout
    type: max-class-fanout
    severity: warning
    limit: 8
    ignore: ["app.CompositionRoot"]

  - id: no-dangling-classes
    type: dangling-classes
    severity: warning
    entry_points: ["app.main.**", "*Controller", "*Command"]
```

Start the two rules as `warning`. On old code, use `scope: diff`, so that only new and
changed classes are examined.

## 14. Guardrails that stay

**Decision:** "Nobody deletes a constraint tag to make a change pass."

Add this entry to each project that uses tags.

```yaml
  - id: freeze-architectural-tags
    type: frozen-rules
    severity: error
    scope: diff
    message: |
      The tag '{rule}' on '{member}' of '{qualified_name}' was {action}. Put the tag
      back, or get the change approved as a design change.
```

The rule compares the code with `.cdec/reference.xmi`. A new tag is protected only after
it is in the reference. After the team approves new tags, a person approves
`cdec reference set <model>` or `cdec check --automatic-exceptions reference`.

## 15. A fast set and a full set

**Decision:** "The fast rules run on each commit. The full set runs before a release."

Move the `rules:` list out of `.cdec/rules.yaml` into two files:

```
.cdec/rules/fast.yaml       # dependency and naming rules
.cdec/rules/release.yaml    # tag-conformance, implementation-locks, reference-architecture
```

```bash
cdec check --rules-file fast      # in the pre-commit hook
cdec check                        # in CI: each file
```

Each file has a `rules:` list and nothing else. The exception keys are the same in the two
runs.

## 16. Closed set of building blocks

**Decision:** "A new class in this subsystem extends `Notifier` or `Channel`. A different
kind of class needs the approval of the architect."

```yaml
  - id: new-classes-use-the-building-blocks
    type: new-class-constraints
    severity: error
    scope: diff
    bases: ["Notifier", "Channel"]
    python:
      forbid_metaclass: ["*"]
    csharp:
      require_modifiers: ["sealed"]
    ignore: ["tests.**"]
    message: |
      Class '{qualified_name}' {reason}. A new class in this subsystem extends
      `Notifier` or `Channel`. To add a different building block, propose it
      first: add it to the model and run `cdec propose`.
```

The rule examines only a class that is not in the baseline. A baseline class passes, also
when it has no approved base. Thus the rule can start on old code with no exceptions.

Put a constraint that exists in one language in the block of that language. `cdec check`
ignores the block of a different language. Keep only the block of the project language, or
keep the two blocks when one entry serves projects in the two languages.

**Passes:** `class SmsNotifier(Notifier)`. `class HtmlEmailNotifier(EmailNotifier)` also
passes, because `EmailNotifier` extends `Notifier`.

**Fails:** `class RetryPolicy:` has no approved base.
`class PushNotifier(Notifier, metaclass=Registry)` declares a metaclass. Each broken
constraint is one issue with its own key.

To approve one class that breaks the rule, a person runs
`cdec exceptions allow <key> --reason "..."`. To approve a new building block, add its name
to `bases` also.

**Trap:** the baseline decides which classes are new. The rule needs `.cdec/reference.xmi`
or `--base-ref`. With no baseline, the rule is skipped. After a person approves
`cdec reference set <model>`, each class of that model is a baseline class, and the rule
does not examine it again. Correct the open issues before the reference changes.

---

## A full example

A `.cdec/rules.yaml` for a Python service with ports and adapters:

```yaml
language: python
source: src
reference: .cdec/reference.xmi

rules:
  - id: layering
    type: layer-dependencies
    severity: error
    allow:
      presentation:   [application, domain]
      application:    [domain]
      domain:         []
      infrastructure: [domain]
    message: |
      Layering violation: '{source}' ({source_layer}) references '{target}'
      ({target_layer}). Define the interface in the lower layer and implement it
      in the higher layer.

  - id: no-cyclic-package-dependencies
    type: no-cyclic-package-dependencies
    severity: error

  - id: tags-must-be-honoured
    type: tag-conformance
    severity: error

  - id: freeze-architectural-tags
    type: frozen-rules
    severity: error
    scope: diff

  - id: frozen-implementations
    type: implementation-locks
    severity: error

  - id: bounded-class-fanout
    type: max-class-fanout
    severity: warning
    limit: 8
```
