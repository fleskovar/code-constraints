# C#

> Runs against **[`examples/csharp_demo`](../../examples/csharp_demo)** — the C# twin of the
> Python bookstore, plus **[`examples/csharp_mvc_demo`](../../examples/csharp_mvc_demo)**, a
> minimal MVC template built around `[Layer]` and the `layer-dependencies` rule. Every
> command below is copy-pasteable from the repository root.

C# has the **most precise** `tag-conformance` of any supported language: construction detection keys
off grammar node kinds rather than guessing from names, so there are essentially no false
positives to suppress.

| | |
|---|---|
| Parser | `tree-sitter-c-sharp` (syntactic — no semantic resolution) |
| Tags | `[Sealed]`, `[Layer("…")]`, … — attributes |
| Shim | `CodeConstraintsRules.cs` (`using CodeConstraints.Rules;` gates recognition) |
| `enforce` | ✅ precise — `object_creation_expression` |
| `lock` | ✅ `cs-ts/1` |
| Activity / sequence | ✅ |

---

## 1. How C# maps onto a UML model

- **Namespaces** become packages. Both forms work: classic `namespace Foo { … }` and
  file-scoped `namespace Foo;` (which claims every subsequent top-level declaration).
- **Classes, interfaces, structs, records and enums** all become classes with the matching
  kind. `static` and `abstract` modifiers set the kind too.
- **Fields and properties** become attributes; **methods and constructors** become
  operations.
- **Inheritance** comes from the base list.

### ⚠️ No semantic resolution

tree-sitter is a syntactic parser. An inheritance line or type reference that goes through a
`using` alias renders as **the alias**, not the qualified name. This is the single most
important thing to know when writing `forbidden-references` patterns for C# — match on what
the source text says, not on what the compiler would resolve.

---

## 2. Parse and look at it

```bash
cdec parse examples/csharp_demo --lang csharp --out demo.xmi
cdec serve            # http://127.0.0.1:8765
```

---

## 3. Writing tags

```bash
cdec update-assets      # drops CodeConstraintsRules.cs into the project
```

```csharp
using CodeConstraints.Rules;

[Immutable]
[Sealed]
[Layer("orders")]
public class Receipt
{
    public double Total { get; }
    public int Lines { get; }

    [Locked(Reason = "receipt wording is contractual; finance signed off on it")]
    public string Formatted() => $"{Lines} line(s) — {Total:F2}";
}

[Factory(Creates = new[] { "Receipt" })]
[Layer("orders")]
public class ReceiptFactory
{
    public Receipt ForCart(Cart cart) => new Receipt(cart.Total(), cart.Items.Count);
}

[NoInstantiation(Allow = new[] { "AuditEntry" })]
[Layer("orders")]
public class CheckoutService { … }
```

Attribute arguments use C# named-argument syntax (`Reason = …`, `Allow = new[]{…}`), and the
optional `Attribute` suffix is tolerated (`[SealedAttribute]` works).

### The gate

An attribute counts as a rule **only when the file has `using CodeConstraints.Rules;`** — or
the attribute is written fully qualified. Your own `[Sealed]` is never mistaken for the
architectural one. If a badge isn't showing up, check the `using` first.

---

## 4. the model rules — architectural drift (`cdec check`)

```bash
cdec check --config examples/csharp_demo/.cdec --source examples/csharp_demo
```

`examples/csharp_mvc_demo` is the demo to read for **tag-driven layering** — it wires
`[Layer("…")]` to the `layer-dependencies` allow-matrix, where the bookstore demos use
`forbidden-package-references` on package paths instead. See its
[README](../../examples/csharp_mvc_demo/README.md).

---

## 5. `tag-conformance` — implementation conformance (the `tag-conformance` rule)

```bash
cdec check --config examples/csharp_demo/.cdec --source examples/csharp_demo
```

```
[tags-must-be-honoured] (error) — 3 finding(s):
  - [F-4BFE2AF0] [factory] Orders/Billing.cs:97: 'Orders.CheckoutService.QuickReceipt'
      constructs 'Receipt' outside its designated factory (ReceiptFactory).
  - [F-B8976F60] [no-instantiation] Orders/Billing.cs:97: 'Orders.CheckoutService.QuickReceipt'
      is tagged [NoInstantiation] but constructs 'Receipt'.
  - [F-6EAFACB5] [no-instantiation] Orders/Order.cs:25: 'Orders.Order.Place'
      is tagged [NoInstantiation] but constructs 'Cart'.
```

**Detection is precise.** Construction is an `object_creation_expression` /
`array_creation_expression` node — not a guess from the callee's name — so unlike Python you
should rarely need `Allow = new[]{…}` to silence a false positive.

**`immutable`** matches `this.<field>` access and bare assignment to a known field outside
the constructor.

**`sealed`** is structural: the tag compared against every other class's base list.

---

## 6. `implementation-locks` — implementation freeze (the `implementation-locks` rule)

```bash
cdec locks examples/csharp_demo --lang csharp --config examples/csharp_demo/.cdec
# ok   Orders.Receipt.Formatted  method  (tag)  Orders/Billing.cs:50
```

The `cs-ts/1` fingerprinter **walks anonymous children too**. Operators and punctuation are
anonymous tokens, so skipping them would hash `a + b` and `a - b` identically. Comments *are*
nodes in this grammar, so they're dropped explicitly, as is the `[Locked]` attribute itself
(recursively — including a method-level lock nested inside a locked class).

**Overloads group into one target.** Every `Formatted(...)` overload shares the digest for
`Orders.Receipt.Formatted`, so adding an overload to a locked name is a violation in its own
right and no ordinal disambiguator is needed.

---

## 7. Parser gotchas worth knowing

These bit us during development and are locked by tests — worth knowing if you extend the
parser or debug an odd model:

**Inheritance lives in an unnamed `base_list` child.** `child_by_field_name("bases")` returns
`None`; the parser iterates `children` matching `node.type == "base_list"`.

**Field types live on the inner `variable_declaration`, not the outer `field_declaration`.**
Reading `type` off the `field_declaration` silently returns `None` and produces typeless
attributes — a regression that once broke struct fields like `public float Damage;`.
Properties put `type` on the property node itself and always worked.

**Arrow-bodied methods expose their `arrow_expression_clause` as the `body` field**, so
collecting both the body field and arrow children double-counts (dedupe by node id).

**`this.field` uses a node of type `this`**, not `this_expression`.

---

## 8. Activity and sequence diagrams

```csharp
// <uml-sequence name="login" root="HandleLogin">
public void HandleLogin(User u) {
    _auth.Verify(u);
    _session.Start(u);
}
// </uml-sequence>
```

```bash
cdec render demo.xmi --diagram sequence --name login -o login.svg
```

Sequence diagrams still render through Graphviz (a static SVG); class, package and activity
diagrams render on the interactive SvelteFlow canvas.

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
- **[Language guides index](README.md)** — how C# compares to the others.
