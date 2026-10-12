# Constraint tags

A tag puts a design constraint on the declaration of a class or a method. `cdec` records
each tag in the model, shows it as a badge on the diagram, and includes it in the diff.

## The seven tags

| Tag id | Goes on | Meaning | What enforces it |
| --- | --- | --- | --- |
| `layer` | class | The class is in the named architectural layer. | The `layer-dependencies` rule |
| `sealed` | class | No class extends this class. | The `tag-conformance` rule |
| `immutable` | class | No method assigns to a field after construction. | The `tag-conformance` rule |
| `factory` | class, method | Only this class constructs the types in `creates`. | The `tag-conformance` rule |
| `no-instantiation` | class, method | The body constructs no object, except the types in `allow`. | The `tag-conformance` rule |
| `no-side-effects` | method | The method has no side effect. | Nothing examines the body. `frozen-rules` protects the tag. |
| `locked` | class, method, function | The implementation is frozen. | The `implementation-locks` rule |

A tag enforces nothing until its rule is in `.cdec/rules.yaml`. Add a `frozen-rules` rule
too, or a developer can delete the tag to make a check pass.

## How to write each tag

| Tag id | Python | C# | Julia |
| --- | --- | --- | --- |
| `layer` | `@layer("domain")` | `[Layer("domain")]` | `@layer "domain"` |
| `sealed` | `@sealed` | `[Sealed]` | `@sealed` |
| `immutable` | `@immutable` | `[Immutable]` | `@immutable` |
| `factory` | `@factory(creates=["Receipt"])` | `[Factory(Creates = new[] { "Receipt" })]` | `@factory creates=["Receipt"]` |
| `no-instantiation` | `@no_instantiation(allow=["AuditEntry"])` | `[NoInstantiation(Allow = new[] { "AuditEntry" })]` | `@no_instantiation allow=["AuditEntry"]` |
| `no-side-effects` | `@no_side_effects` | `[NoSideEffects]` | `@no_side_effects` |
| `locked` | `@locked(reason="...", owner="...")` | `[Locked(Reason = "...", Owner = "...")]` | `@locked reason="..."` |

| Tag id | Lua | Odin |
| --- | --- | --- |
| `layer` | `---@cdec layer("domain")` | `//@cdec layer("domain")` |
| `sealed` | `---@cdec sealed` | `//@cdec sealed` |
| `immutable` | `---@cdec immutable` | `//@cdec immutable` |
| `factory` | `---@cdec factory(creates = {"Receipt"})` | `//@cdec factory(creates = ["Receipt"])` |
| `no-instantiation` | `---@cdec no_instantiation(allow = {"AuditEntry"})` | `//@cdec no_instantiation(allow = ["AuditEntry"])` |
| `no-side-effects` | `---@cdec no_side_effects` | `//@cdec no_side_effects` |
| `locked` | `---@cdec locked(reason = "...")` | `//@cdec locked(reason = "...")` |

TypeScript and Svelte have no tags. Use rules in `.cdec/rules.yaml` for these languages.

## The shim

In Python, C# and Julia, a tag is a decorator, an attribute or a macro that does nothing
at run time. It comes from a shim file. Copy the shim into the project:

```bash
cdec update-assets --no-agents     # for Python, writes cdec_rules.py
```

The command reads the language from `.cdec/rules.yaml`. Before `cdec init`, give it
`--lang <language>`.

| Language | Shim file | The import that makes the tags valid |
| --- | --- | --- |
| Python | `cdec_rules.py` | `from cdec_rules import layer, sealed, immutable, factory, no_instantiation, no_side_effects, locked` |
| C# | `CodeConstraintsRules.cs` | `using CodeConstraints.Rules;` |
| Julia | `CdecRules.jl` | `using CdecRules` |
| Lua | `cdec_rules.lua` | None. The `@cdec` prefix in the comment is the namespace. |
| Odin | `cdec_rules.odin` | None. The `@cdec` prefix in the comment is the namespace. |

**`cdec` recognises a tag only when the shim is in scope.** A file that has `@sealed` and
no import from `cdec_rules` has no tag. If a tag does not show in the diagram, examine the
import first.

## Traps for each language

- **Julia.** The arguments are separated by spaces. `@layer "domain"` is correct.
  `@layer("domain")` is a syntax error.
- **Lua and Odin.** The comment must be on the line directly above the declaration. An
  empty line between them removes the tag.
- **Lua.** A list argument uses braces: `{"Receipt"}`. Odin and Julia use brackets.
- **Python.** `tag-conformance` has no type resolution. A call to a project class or to a
  capitalised name counts as a construction. `Decimal("1.00")` and `Path(p)` thus count.
  Put such types in `allow=[...]`.

How `tag-conformance` finds a construction:

| Language | Method | Result |
| --- | --- | --- |
| C#, Odin | The grammar marks a construction. | Exact. `allow` is rarely necessary. |
| Python | A call to a capitalised name or to a project class. | False positives are possible. Use `allow`. |
| Julia | A call to a type that the parse found. | No false positive. A type from outside the parse is missed. |
| Lua | `T.new(...)` and `setmetatable(t, T)`. | An unusual constructor convention is missed. |

In Lua, Odin and Julia, a type can always construct itself.

## Each tag in detail

The examples are in Python. The other languages use the same meaning.

### `layer`

Declares the layer of a class. The `layer-dependencies` rule reads it. The argument is the
layer name.

```python
@layer("domain")
class Order: ...
```

### `sealed`

Fails when a class of the project extends the tagged class. The match is by short name.

```python
@sealed
class Receipt: ...

class DiscountedReceipt(Receipt): ...      # fails

class AnnotatedReceipt:                    # passes: it holds a Receipt
    def __init__(self, receipt: Receipt, note: str) -> None: ...
```

### `immutable`

Fails when a method that is not the constructor assigns to a field of the class.

```python
@immutable
class Receipt:
    def __init__(self, total: float) -> None:
        self.total = total                               # passes: the constructor

    def with_discount(self, pct: float) -> "Receipt":
        return Receipt(self.total * (1 - pct))           # passes: a new object

    def apply_discount(self, pct: float) -> None:
        self.total *= (1 - pct)                          # fails
```

### `factory`

Fails when a type in `creates` is constructed outside the class that has the tag. The
argument `creates` is a list of short type names. If the tag is on a method, the class of
that method is the factory.

```python
@factory(creates=["Receipt"])
class ReceiptFactory:
    def for_cart(self, cart: Cart) -> Receipt:
        return Receipt(cart.total())                     # passes: this is the factory

class CheckoutService:
    def quick_receipt(self, cart: Cart) -> Receipt:
        return Receipt(cart.total())                     # fails
```

### `no-instantiation`

Fails when the tagged class or method constructs an object whose type is not in `allow`.
With no `allow`, the body constructs nothing. A tag on a method replaces the tag of its
class for that method.

```python
@no_instantiation(allow=["AuditEntry"])
class CheckoutService:
    def __init__(self, receipts: ReceiptFactory) -> None:
        self.receipts = receipts                         # injected

    def checkout(self, cart: Cart) -> Receipt:
        self.audit(AuditEntry("checkout"))               # passes: in allow
        return self.receipts.for_cart(cart)              # passes: delegated

    def quick(self, cart: Cart) -> Receipt:
        return Receipt(cart.total())                     # fails
```

### `no-side-effects`

Declares that a method is pure. No check examines the body. The tag is documentation that
`frozen-rules` protects: after the tag is in the baseline, its removal fails the gate.

```python
class PriceCalculator:
    @no_side_effects
    def subtotal(self, cart: Cart) -> float: ...
```

### `locked`

Declares that an implementation is frozen. `reason` says why. `owner` says who approves a
change. The `implementation-locks` rule compares the syntax tree with a recorded digest.

```python
class Receipt:
    @locked(reason="the receipt wording is contractual; finance approved it")
    def formatted(self) -> str:
        return f"{self.lines} line(s) - total {self.total:.2f}"
```

After you add the tag, a person approves `cdec check --automatic-exceptions locks`, which
records the digest. A later change to the body fails the gate. The deletion of the tag
also fails the gate, because the recorded digest stays.
