# Julia

> Runs against **[`examples/julia_demo`](../../examples/julia_demo)** — a `catalog` +
> `orders` slice of the bookstore domain with a fully tagged `Billing` module and one
> intentional violation. Every command below is copy-pasteable from the repository root.

Julia support is complete: parser, all seven constraint tags as **real macros**, `cdec
enforce` (Engine B) with name-based construction detection, and `cdec lock` (Engine C) with
the `jl-ts/1` fingerprinter. Activity and sequence diagrams are not implemented for Julia.

Julia is the only one of the newer languages with a first-class construct to hang a tag on,
so its tags read almost exactly like Python decorators — with one syntax trap (§3).

| | |
|---|---|
| Parser | `tree-sitter-julia` (syntactic — no method-table resolution) |
| Tags | `@sealed`, `@layer "orders"`, … — real macros |
| Shim | `CdecRules.jl` (no-op macros; `using CdecRules` gates recognition) |
| `enforce` | ✅ name-based — a call whose callee is a project type |
| `lock` | ✅ `jl-ts/1` |
| Activity / sequence | ❌ |

---

## 1. How Julia maps onto a UML model

### Types become classes

```julia
abstract type AbstractInvoice end       # → class (kind: abstract)

struct Money                            # → class (kind: struct)
    amount::Float64
    currency::String
end

mutable struct Draft
    lines::Vector{String}               # type kept verbatim: "Vector{String}"
end

struct Invoice <: AbstractInvoice       # → Invoice inherits AbstractInvoice
    id::String
end
```

A non-`mutable struct` genuinely cannot be reassigned, so its fields are modelled as
**read-only**. `mutable struct` fields are not.

### Functions belong to their first argument's type

Julia has no methods-inside-types. `cdec` attributes a function to the type of its **first
argument**, which is the honest reading of single-argument dispatch:

```julia
formatted(r::Receipt)::String = "…"     # → operation `formatted` on Receipt
```

Its qualified name is `orders.Billing.Receipt.formatted` — that is what the diagram shows,
what `cdec lock` records, and what `cdec baseline allow` accepts. The receiver is dropped
from the rendered signature.

Both the long form and the **short form** are recognised:

```julia
function summarise(inv::Invoice, verbose::Bool=false; short=true) … end
total_of(inv::Invoice) = inv.total      # short form — also an operation on Invoice
```

Because a function and its struct can live in different files, the parser is **two-phase**:
all types are registered first, then functions attached. Resolution prefers the same
package, then a project-wide match *only if unambiguous*.

**Inner constructors** are ingested as operations of their own struct, so a `@locked` inner
constructor is lockable like any other member:

```julia
struct Invoice
    id::String
    Invoice(id) = new(id)               # → operation `Invoice` on Invoice
end
```

### Packages: directories, then modules

Package names come from the directory layout, with each `module X … end` nesting further
inside it — the same scheme the TypeScript parser uses for `namespace`. So
`orders/Billing.jl` declaring `module Billing` yields the package `orders.Billing`.

### Receiver-less functions become a `static` class

```julia
helper(x::Int) = x + 1                  # Int isn't a project type
```

lands on a synthetic `static` class named after the **file stem** — so free functions from
every module in one file share one class, and a tag on them is never dropped.

---

## 2. Parse and look at it

```bash
cdec parse examples/julia_demo --lang julia --out julia.xmi
cdec serve            # http://127.0.0.1:8765 — register the folder, pick "julia"
```

---

## 3. Writing tags

Bring the shim into scope, then tag as you would with a decorator:

```julia
using CdecRules

@immutable @sealed @layer "orders" struct Receipt
    total::Float64
    lines::Int
end

@locked reason="receipt wording is contractual" function formatted(r::Receipt)::String
    return string(r.lines, " line(s) — ", round(r.total; digits=2))
end
```

### ⚠️ Arguments are space-separated, not parenthesised

This is the one Julia trap, and it is a **syntax error**, not a silent miss:

```julia
@layer "orders" struct Order end     # ✅ correct
@layer("orders") struct Order end    # ❌ Julia syntax error
```

Keyword arguments follow the same shape:

```julia
@locked reason="why" owner="ann" function f(x::Invoice) … end
@no_instantiation allow=["Money"] function g(x::Invoice) … end
@factory creates=["Receipt"] mutable struct ReceiptFactory
    issued::Int
end
```

Stacking works in any order and reads left to right.

### The gate

A macro counts as a rule **only when the file brings the shim into scope** —
`using CdecRules` or `import CdecRules`. Your own `@sealed` is never mistaken for the
architectural one, and a file that forgets the import silently has no tags at all. If a
badge isn't showing up, check the `using` line first.

```bash
cdec update-assets      # drops CdecRules.jl into the project root
```

Every macro in the shim is variadic and returns its final argument, so stacking works in any
order and an unknown extra argument is ignored rather than erroring. Parsers skip the shim
file itself, so its macro definitions never appear in your diagrams.

**Non-rule macros are peeled, not fatal.** `Base.@kwdef struct … end` still yields the
struct — an unrelated wrapper never hides a type from the model.

---

## 4. Engine A — architectural drift (`cdec check`)

```bash
cdec check --config examples/julia_demo/.cdec --source examples/julia_demo
# cdec check: no violations.
# cdec lock: 1 locked element(s) verified, no changes.
```

Freeze the tags themselves so a constraint can't be silenced by deleting a macro:

```yaml
- id: freeze-architectural-tags
  type: frozen-rules
  scope: diff
  classes: ["orders.**"]
```

Remove `@sealed` from the `Receipt` declaration and re-run:

```
[V-D1B65CE8] orders.Billing.Receipt — orders/Billing.jl:38:
  Architectural tag drift: the rule 'sealed' on 'orders.Billing.Receipt' was removed.
```

---

## 5. Engine B — implementation conformance (`cdec enforce`)

```bash
cdec enforce examples/julia_demo --lang julia
```

```
cdec enforce: 2 conformance violation(s):
  - [F-DAB2D2F6] [factory] orders/Billing.jl:81: 'orders.Billing.CheckoutService.quick_receipt'
      constructs 'Receipt' outside its designated factory (ReceiptFactory).
  - [F-92E7A54D] [no-instantiation] orders/Billing.jl:81: 'orders.Billing.CheckoutService.quick_receipt'
      is tagged @no_instantiation but constructs 'Receipt'.
```

### Detection is name-based — and that's a deliberate trade

**Julia construction has no dedicated syntax.** `Money(1.0)` is an ordinary call,
indistinguishable at the grammar level from `round(1.0)`. So a call counts as a construction
only when its callee is the name of a type **this parse saw**.

That is narrower than Python's "callee is Capitalised" heuristic:

- ✅ no false positives on stdlib calls,
- ⚠️ constructions of types the parse didn't see (a dependency's type) are **missed**.

**`immutable`** detection is precise — an `assignment` whose target is a `field_expression`
rooted at the receiver argument. Note a plain `struct` is already immutable to the compiler;
the tag earns its keep on `mutable struct`, where it says the mutability is an
implementation detail operations may not use.

**A type may always construct itself**, so inner constructors are never flagged.

**`sealed`** needs no body analysis and is fully reliable — it compares the tag against
every other type's `<:` supertype:

```julia
@sealed abstract type Base end
struct Derived <: Base end        # → [sealed] 'Derived' subclasses sealed 'Base'
```

`@sealed` is most meaningful on `abstract type`, since that is where Julia subtyping is
actually possible.

### Escape hatches

```julia
@no_instantiation allow=["AuditEntry"] struct CheckoutService
    receipts::ReceiptFactory
end
```

```bash
cdec baseline allow F-92E7A54D --config examples/julia_demo/.cdec --reason "legacy path, ticket #142"
```

---

## 6. Engine C — implementation freeze (`cdec lock`)

```bash
cdec lock list examples/julia_demo --lang julia --config examples/julia_demo/.cdec
# ok   orders.Billing.Receipt.formatted  method  (tag)  orders/Billing.jl:43
```

```bash
cdec lock set   examples/julia_demo --lang julia --config examples/julia_demo/.cdec --reason "…"
cdec lock check examples/julia_demo --lang julia --config examples/julia_demo/.cdec
```

Two Julia-specific behaviours:

**Multiple dispatch collapses into one target.** Every method of `settle(::Invoice, …)`
groups into the single target `orders.Billing.Invoice.settle`, so **adding a new dispatch to
a locked name is itself a lock violation**. Those methods may live in different files.

**The tag wraps the definition rather than preceding it.** The digest is therefore taken over
the *unwrapped* definition — which is what makes applying or removing `@locked` leave the
digest untouched. Non-rule macros are folded back in separately, so:

| Change | Digest |
|---|---|
| add / remove `@locked` | unchanged ✅ |
| add / remove `@inline` | **changed** — a real change |
| comment edits, reformatting, moving the function | unchanged ✅ |
| any semantic change to the body | **changed** |

Re-baselining stays privileged:

```bash
cdec lock set examples/julia_demo --lang julia \
  --target orders.Billing.Receipt.formatted --force --reason "approved"
```

---

## 7. Gotchas

**`@layer("orders")` is a syntax error.** Macro arguments are space-separated. This is the
single most common Julia mistake — see §3.

**No `using CdecRules`, no tags.** The import is the gate. A file without it parses fine and
silently has zero tags.

**Comments are `line_comment` / `block_comment`.** Only relevant if you're extending the
parser — Julia is the one grammar here that has no plain `comment` node.

**A function whose first argument isn't a project type is not a method.** It lands on the
file's `static` module class instead. Check the first argument's annotation.

**An untyped first argument means no receiver.** `f(x) = …` has nothing to dispatch on, so
it is a free function as far as the model is concerned.

---

## 8. CI

```yaml
- run: cdec check   --config .cdec --source .   # Engine A + C
- run: cdec enforce . --lang julia              # Engine B
```

See [Tutorial Part 9](../TUTORIAL.md#part-9--wiring-up-cicd) for full workflows.

---

## Where to go next

- **[Tutorial](../TUTORIAL.md)** — the full workflow including the design loop.
- **[Rules catalogue](../RULES_CATALOGUE.md)** — every rule and tag in detail.
- **[Language guides index](README.md)** — how Julia compares to the others.
