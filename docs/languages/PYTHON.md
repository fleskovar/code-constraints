# Python

> Runs against **[`examples/python_demo`](../../examples/python_demo)** — a four-package
> bookstore (`catalog`, `users`, `orders`, `notifications`) with a fully tagged `billing`
> slice and one intentional violation. Every command below is copy-pasteable from the
> repository root.

Python is the most fully supported language: everything works, including activity and
sequence diagrams. It is also the language where `tag-conformance`'s construction detection is
**heuristic** — the one place you should expect to reach for `allow=[…]`.

| | |
|---|---|
| Parser | stdlib `ast` (no third-party grammar) |
| Tags | decorators from `cdec_rules` |
| Shim | `cdec_rules.py` |
| `enforce` | ⚠️ heuristic — no type resolution |
| `lock` | ✅ `py-ast/1` |
| Activity / sequence | ✅ |

---

## 1. How Python maps onto a UML model

Mostly one-to-one, which is why Python is the easiest starting point.

- **Packages** mirror the directory layout.
- **Classes** come from `ClassDef`; kind is inferred from the bases — `ABC` → abstract,
  `Enum`/`IntEnum` → enum, `Protocol` → interface, `metaclass=ABCMeta` → abstract.
- **Operations** come from `FunctionDef` / `AsyncFunctionDef`.
- **Class attributes** come from annotated and plain assignments in the class body.
- **Instance attributes** are recovered from `self.x = …` **in `__init__` only**. (Lua, by
  contrast, has no constructor convention to privilege and so scans every method.)
- A leading underscore marks private by convention.

Module-level functions are not modelled — Python has real classes, so there is no need for
the synthetic `static` module class that Odin, Lua and Julia use.

---

## 2. Parse and look at it

```bash
cdec parse examples/python_demo --lang python --out demo.xmi
cdec serve            # http://127.0.0.1:8765
```

`--lang` is auto-detected from the file mix when omitted.

---

## 3. Writing tags

```bash
cdec update-assets      # drops cdec_rules.py into the project root
```

```python
from cdec_rules import factory, immutable, layer, locked, no_instantiation, sealed

@immutable
@sealed
@layer("orders")
class Receipt:
    def __init__(self, total: float, lines: int) -> None:
        self.total = total
        self.lines = lines

    @locked(reason="receipt wording is contractual; finance signed off on it")
    def formatted(self) -> str:
        return f"{self.lines} line(s) — {self.total:.2f}"


@factory(creates=["Receipt"])
@layer("orders")
class ReceiptFactory:
    def for_cart(self, cart: Cart) -> Receipt:
        return Receipt(cart.total(), len(cart.items))   # OK: this is the factory


@no_instantiation(allow=["AuditEntry"])
@layer("orders")
class CheckoutService: ...
```

### The gate

A decorator counts as a rule **only when its base name was imported from the shim** —
`from cdec_rules import …` (or `code_constraints.rules`). Your own decorator called `sealed`
is never mistaken for the architectural one, and a file that forgets the import silently has
no tags at all. If a badge isn't showing up, check the import first.

Aliased imports work: `from cdec_rules import sealed as final` is still recognised.

---

## 4. the model rules — architectural drift (`cdec check`)

```bash
cdec check --config examples/python_demo/.cdec --source examples/python_demo
# cdec check: no violations.
# cdec lock: 1 locked element(s) verified, no changes.
```

The demo's `rules.yaml` is the fullest of the bundled sets — package layering, subclass
naming, dangling classes, fanout limits, frozen members on the `Notification` ABC, and
frozen tags on `orders.**`. Read it alongside the
[Rules catalogue](../RULES_CATALOGUE.md).

Delete `@sealed` from `orders.billing.Receipt` and re-run to watch `frozen-rules` fire.

---

## 5. `tag-conformance` — implementation conformance (the `tag-conformance` rule)

```bash
cdec check --config examples/python_demo/.cdec --source examples/python_demo
```

```
[tags-must-be-honoured] (error) — 2 finding(s):
  - [factory]          'CheckoutService.quick_receipt' constructs 'Receipt' outside
                       its designated factory (ReceiptFactory).
  - [no-instantiation] 'CheckoutService.quick_receipt' is tagged @no_instantiation
                       but constructs 'Receipt'.
```

### ⚠️ Detection is heuristic

Python has no type resolution at parse time, so a "construction" is **a call whose callee is
a known project class, or is Capitalised**. That is deliberately generous, and it means:

- a call to a Capitalised factory *function* may be reported as a construction,
- `allow=[…]` is the intended escape hatch, not a workaround.

```python
@no_instantiation(allow=["list", "dict", "AuditEntry"])
def total(self): ...
```

Compare with C# and Odin, where the grammar distinguishes construction outright and no
suppression is needed.

**`immutable`** flags `self.x = …` outside `__init__`.

**`sealed`** is structural and fully reliable — it compares the tag against every other
class's base list.

For a one-off you disagree with, record it in the reviewable ledger:

```bash
cdec exceptions review --config examples/python_demo/.cdec --out review.txt
# mark lines with [ALLOW], then:
cdec exceptions patch --config examples/python_demo/.cdec --file review.txt
```

---

## 6. `implementation-locks` — implementation freeze (the `implementation-locks` rule)

```bash
cdec locks examples/python_demo --lang python --config examples/python_demo/.cdec
# ok   orders.Receipt.formatted  method  (tag)  orders/billing.py:43
```

The `py-ast/1` fingerprinter hand-rolls a canonical serialiser rather than using `ast.dump`,
and **omits fields that are `None` or empty** — so an AST field added by a future CPython
(e.g. `type_params` in 3.12) cannot silently invalidate every digest in your ledger.

Python-specific behaviours:

- **Docstrings are stripped** unless `lock.include_docstrings: true`. A body stripped to
  nothing gets an `ast.Pass()` so it stays valid.
- **Same-named siblings group into one target** — `@property` plus its `@x.setter` share a
  digest, so adding a setter to a locked property is a violation in its own right.
- Position attributes live in `_attributes`, not `_fields`, so moving code never matters.

Targets use the UML qualified name (`orders.Receipt.formatted`); module-level functions
additionally carry the module stem (`orders.billing.compute_tax`), since two modules in a
package may define the same name.

---

## 7. Activity and sequence diagrams

Python and C# are the only languages that support embedded diagram tags:

```python
# <uml-activity name="checkout" granularity="control-flow">
def checkout(cart):
    if cart.is_empty():
        return
    pay(cart)
# </uml-activity>
```

Supported: `<uml-class />`,
`<uml-activity name="…" granularity="control-flow|statement|calls">`,
`<uml-sequence name="…" root="…">`. Tag parsing runs on raw source text *before* the AST
parse (comments aren't in the Python AST) and is intentionally forgiving — a malformed tag is
skipped, never fatal.

---

## 8. Gotchas

**Forgot the shim import → no tags at all**, silently. The most common Python mistake.

**`tag-conformance` over-reports on Capitalised callees.** That's the documented trade for having no
type resolution. Use `allow=[…]`.

**Two attributes with the same signature is legal** — a class-scope `species: str` plus
`self.species = …` in `__init__` produces two attributes. The renderers key on index +
signature to cope.

---

## 9. CI

```yaml
- run: cdec check   --config .cdec --source .   # the model rules + C
```

See [Tutorial Part 9](../TUTORIAL.md#part-9--wiring-up-cicd) for full workflows.

---

## Where to go next

- **[Tutorial](../TUTORIAL.md)** — the full workflow including the design loop.
- **[Rules catalogue](../RULES_CATALOGUE.md)** — every rule and tag in detail.
- **[Language guides index](README.md)** — how Python compares to the others.
