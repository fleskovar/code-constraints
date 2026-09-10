# Example codebases

> These demos are the worked examples used throughout the
> **[Tutorial](../docs/TUTORIAL.md)** — start there if you want a guided path rather than a
> catalogue. `make demo` runs all three engines against the Python and C# demos in one shot.
>
> The `rules.yaml` and tagged classes in these demos are live instances of the constraints
> documented in the **[Rules & constraints catalogue](../docs/RULES_CATALOGUE.md)** — read a
> rule there, then see it configured here.

Small codebases — Python, C#, TypeScript, and a Svelte 5 storefront — all
modelling the same bookstore domain so you can compare languages side-by-side.
The Python and C# demos exercise every diagram kind code-constraints supports;
the TypeScript and Svelte demos focus on class + package diagrams (activity /
sequence tags are not yet recognised in `.ts` / `.svelte` files):

Three more — [`odin_demo`](odin_demo), [`lua_demo`](lua_demo) and
[`julia_demo`](julia_demo) — carry a trimmed `catalog` + `orders` slice of the
same domain. They exist to show how the rule tags read in languages with **no
`class` construct**, where an operation belongs to the type of its first
argument (Odin `proc(r: ^Receipt, …)`, Julia `formatted(r::Receipt)`) or to its
table (Lua `function Receipt:formatted()`). Each is the canonical end-to-end
demo for its language: `cdec check` passes, `cdec check` verifies the
frozen `Receipt.formatted`, and the `tag-conformance` rule reports exactly the two seeded
findings in `quick_receipt`.

```bash
cdec check   --config examples/odin_demo/.cdec --source examples/odin_demo  # passes
cdec enforce examples/odin_demo --lang odin                                 # 2 findings
```

Note the tag syntax differs by language, and deliberately so — each demo's guide explains
why, and walks the whole workflow in that language:

| Demo         | Tag form                                | Shim                | Guide |
| ------------ | --------------------------------------- | ------------------- | ----- |
| `python_demo`| `@sealed` decorator                      | `cdec_rules.py`     | [Python](../docs/languages/PYTHON.md) |
| `csharp_demo`| `[Sealed]` attribute                     | `CodeConstraintsRules.cs` | [C#](../docs/languages/CSHARP.md) |
| `julia_demo` | `@sealed` macro (args are space-separated: `@layer "orders"`) | `CdecRules.jl` | [Julia](../docs/languages/JULIA.md) |
| `lua_demo`   | `---@cdec sealed` annotation comment     | `cdec_rules.lua`    | [Lua](../docs/languages/LUA.md) |
| `odin_demo`  | `//@cdec sealed` annotation comment      | `cdec_rules.odin`   | [Odin](../docs/languages/ODIN.md) |

The [**per-language guides index**](../docs/languages/README.md) has the full capability
matrix and explains how languages without a `class` construct map onto a UML model.

Another demo, [`csharp_mvc_demo`](csharp_mvc_demo), stands apart from the
bookstore set: it's a minimal Model-View-Controller template that showcases the
`@layer` tag and the **`layer-dependencies`** rule (the tag-driven layering
check the bookstore demos don't use — they enforce layering with
`forbidden-package-references` instead). See its
[README](csharp_mvc_demo/README.md).

| Diagram kind   | Where it lives in the demos                                                     |
| -------------- | ------------------------------------------------------------------------------- |
| Class          | every `.py` / `.cs` file — all classes, enums, interfaces                       |
| Package        | derived from the 4 packages: `catalog`, `users`, `notifications`, `orders`      |
| Activity (control-flow)  | `Cart.checkout` (`cart_checkout`)                                     |
| Activity (statement)     | `Book.is_available` / `Book.IsAvailable` (`book_availability`)        |
| Sequence       | `Cart.add_item` / `Cart.AddItem` (`cart_add_item`); `Order.place` / `Order.Place` (`order_place`) |

## Domain at a glance

```
catalog        users                notifications        orders
 Author         User (abstract)      Notification (abs)   OrderItem
 Book ──┐       ├─ Customer ─┐        ├─ EmailNotifier    Cart
        │       └─ Admin     │        └─ SmsNotifier      Order
        │                    │                            OrderStatus (enum)
        └──── OrderItem.book │
                             └──── Customer.notifier
```

Cross-package dependencies you should see in the **package diagram**:

- `orders` → `catalog` (OrderItem references Book)
- `orders` → `users` (Cart references Customer)
- `users` → `notifications` (Customer references Notification / INotifier)

## Running the demos

Start the server:

```bash
.venv/Scripts/python.exe -m code_constraints.cli serve
# → http://127.0.0.1:8765
```

In the UI: **Change project** → paste an absolute path to any of the demos:

- Python: `<repo>/examples/python_demo`, language **python**
- C#: `<repo>/examples/csharp_demo`, language **csharp**
- TypeScript: `<repo>/examples/typescript_demo`, language **typescript**
- Svelte 5: `<repo>/examples/svelte_demo`, language **svelte**
- C# MVC: `<repo>/examples/csharp_mvc_demo`, language **csharp**

Or do the same from the CLI:

```bash
# parse to XMI
.venv/Scripts/python.exe -m code_constraints.cli parse examples/python_demo --lang python --out demo.xmi

# render a single class diagram to SVG (requires Graphviz `dot`)
.venv/Scripts/python.exe -m code_constraints.cli render demo.xmi --diagram class -o class.svg
```

## Architectural rule tags & constraints

The Python and C# demos each carry a **`billing` slice**
([`python_demo/orders/billing.py`](python_demo/orders/billing.py),
[`csharp_demo/Orders/Billing.cs`](csharp_demo/Orders/Billing.cs)) that puts all
five v1 rule tags on real classes. Tags are declared via shipped no-op shims
(`shims/python/cdec_rules.py`, `shims/csharp/CodeConstraintsRules.cs`) under a
dedicated namespace, so tagged code still imports/compiles and the parser never
false-matches an unrelated decorator/attribute.

| Tag | Python | C# | Meaning | In the demo |
| --- | --- | --- | --- | --- |
| no-instantiation | `@no_instantiation(allow=[...])` | `[NoInstantiation(Allow = ...)]` | the body may not construct objects (except `allow`-listed types) | `CheckoutService` delegates construction to the factory |
| factory | `@factory(creates=[...])` | `[Factory(Creates = ...)]` | the *only* place allowed to build the listed types | `ReceiptFactory` is the sole `Receipt` constructor |
| immutable | `@immutable` | `[Immutable]` | fields may not be reassigned after construction | `Receipt` is built once, never mutated |
| sealed | `@sealed` | `[Sealed]` | the class may not be subclassed | `Receipt` has no subtypes |
| layer | `@layer("name")` | `[Layer("name")]` | assigns the class to an architectural layer | every billing class is `@layer("orders")` |

The tags **show up as colour-coded badges** on the tagged classes/operations in
the web class diagram (hover for the rule + parameters), **round-trip through
XMI**, and **participate in the diff**.

### Two decoupled enforcement engines

Enforcement is split into two independent commands — one for *architecture*, one
for *implementation*:

```bash
# Engine A — `cdec check` (drift): operates on the model + baseline only,
# never inspects method bodies. PASSES on the demo (architecture is intact).
.venv/Scripts/python.exe -m code_constraints.cli check --config examples/python_demo/.cdec --source examples/python_demo

# Engine B — the `tag-conformance` rule (implementation conformance): re-parses the source
# and inspects method bodies. FLAGS the seeded violation below.
.venv/Scripts/python.exe -m code_constraints.cli enforce examples/python_demo --lang python
```

the `tag-conformance` rule reports the **one intentional violation** baked into each demo —
`CheckoutService.quick_receipt` builds a `Receipt` directly instead of going
through the factory, tripping *both* the `no-instantiation` and `factory` rules:

```
cdec enforce: 2 conformance violation(s):
  - [factory] orders/billing.py:97: 'orders.CheckoutService.quick_receipt' constructs 'Receipt' outside its designated factory (ReceiptFactory).
  - [no-instantiation] orders/billing.py:97: 'orders.CheckoutService.quick_receipt' is tagged @no_instantiation but constructs 'Receipt'.
```

Delete that method (or change it to `return self.receipts.for_cart(cart)`) and
the run goes green. Swap `python` → `csharp` and the path for the C# demo, which
seeds the identical violation in `CheckoutService.QuickReceipt`.

Run both engines together with `cdec check`: the lint section passes
while the conformance section flags the body bug — the clearest illustration of
why the two are decoupled.

### Try the drift engine (`frozen-rules`)

Both demos enable a `frozen-rules` lint that freezes the tags recorded in
`reference.xmi`. Remove a tag — e.g. delete `@sealed` from `Receipt` — and
re-run `cdec check`: it fails because an architectural constraint was dropped.
(It never inspects bodies — that's the `tag-conformance` rule's job.) Run
`cdec check --automatic-exceptions reference` to deliberately accept a new baseline.

## Trying the diff view

Both demos live inside this repo, so you can use `git` refs to diff them
against earlier commits once you start evolving them. From the UI: switch the
mode toggle from **Browse** to **Diff** and pick two refs.

## Extending

The codebases are intentionally minimal — about a dozen classes each, no
external deps beyond the standard library. Good places to grow them while you
build new features:

- Add another package (e.g. `shipping`) to stress the package-dependency
  rendering with a fourth node.
- Tag another method as an activity with `granularity="calls"` to exercise the
  third granularity (currently only `control-flow` and `statement` are
  demonstrated).
- Add a second-level inheritance (e.g. `PreferredCustomer(Customer)`) to test
  deeper inheritance hierarchies.
- Add a struct (C#) or `@dataclass` (Python) — both parsers recognise these
  as a distinct `ClassKind`.

## Tag reference

The harness scans source comments before AST parsing. The recognised tags:

```python
class Foo:
    def method(self):
        # <uml-activity name="my_flow" granularity="control-flow">
        # ...code under analysis...
        # </uml-activity>

    def other(self):
        # <uml-sequence name="my_interaction" root="self">
        # ...code where each function call becomes a message...
        # </uml-sequence>
```

`granularity` for activities is one of `control-flow` | `statement` | `calls`.
`root` for sequences names the lifeline that originates the messages (use
`self` for Python, `this` for C#).
