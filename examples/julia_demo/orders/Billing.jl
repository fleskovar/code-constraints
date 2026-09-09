"""
Billing slice — a hands-on tour of the architectural-rule tags in Julia.

This is the part of the demo that exercises **`cdec enforce`** (the
implementation-conformance engine). Every tag here is *satisfied* except for one
clearly-marked, intentional violation in `quick_receipt`, so that:

    cdec enforce examples/julia_demo --lang julia

prints exactly the two findings explained inline below. Delete that function (or
route it through the factory) and the run goes green.

Julia has real macros, so tags look almost exactly like Python decorators — but
two things differ from the Python and C# demos:

* **Macro arguments are space-separated**, not parenthesised: `@layer "orders"`,
  not `@layer("orders")` (the latter is a Julia syntax error). See `CdecRules.jl`.
* **Functions belong to their first argument's type.** `formatted(r::Receipt)` is
  modelled as the operation `formatted` on `Receipt`, so it draws inside the
  Receipt box and `@locked` freezes it like any other method.

The tags on display:

* @no_instantiation — CheckoutService may not build domain objects.
* @factory creates=[...] — ReceiptFactory is the only place allowed to construct
  a Receipt.
* @immutable — a Receipt's fields never change after construction.
* @sealed — there are no specialised Receipt subtypes.
* @layer "orders" — assigns these structs to the `orders` layer.
* @locked — Receipt.formatted's implementation is frozen.
"""
module Billing

using CdecRules

using ..Catalog: Book

@immutable @sealed @layer "orders" struct Receipt
    total::Float64
    lines::Int
end

@locked reason="receipt wording is contractual; finance signed off on it" function formatted(r::Receipt)::String
    # FROZEN by `cdec lock` (Engine C). The digest of this body is recorded in
    # `.cdec/locks.yaml`; changing so much as the separator fails `cdec check`.
    # Try it: swap the em-dash for a comma and re-run
    #     cdec check --config examples/julia_demo --source examples/julia_demo
    # Reformat it or move the function up the file and nothing happens — the
    # lock is over the AST, not the text.
    return string(r.lines, " line(s) — ", round(r.total; digits=2))
end

@layer "orders" struct AuditEntry
    action::String
end

@factory creates=["Receipt"] @layer "orders" mutable struct ReceiptFactory
    issued::Int
end

function for_cart(f::ReceiptFactory, cart)
    f.issued += 1
    return Receipt(total(cart), length(cart.items))  # OK: this is the factory
end

@no_instantiation allow=["AuditEntry"] @layer "orders" struct CheckoutService
    receipts::ReceiptFactory
end

function summarize(s::CheckoutService, cart)
    audit = AuditEntry("summarize")          # OK: whitelisted via `allow`
    receipt = for_cart(s.receipts, cart)     # OK: a call, not a construction
    return string(formatted(receipt), " / ", audit.action)
end

function quick_receipt(s::CheckoutService, cart)
    # INTENTIONAL VIOLATION — two findings fire on the line below:
    #   [no-instantiation] 'CheckoutService.quick_receipt' constructs 'Receipt'
    #   [factory]          'Receipt' may only be built by ReceiptFactory
    # Fix by delegating:  return for_cart(s.receipts, cart)
    return Receipt(total(cart), length(cart.items))
end

end # module Billing
