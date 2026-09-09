/*
Billing slice — a hands-on tour of the architectural-rule tags in Odin.

This is the part of the demo that exercises **`cdec enforce`** (the
implementation-conformance engine). Every tag here is *satisfied* except for one
clearly-marked, intentional violation in `quick_receipt`, so that:

    cdec enforce examples/odin_demo --lang odin

prints exactly the two findings explained inline below. Delete that procedure (or
route it through the factory) and the run goes green.

Odin has no classes and no user-defined attributes, so two things differ from the
Python and C# demos while meaning exactly the same:

* **Tags are `//@cdec` comments** placed where a decorator would go. Odin's
  `@(...)` attributes are a closed set the compiler validates, so a no-op
  `@(cdec_sealed)` would not build. See `cdec_rules.odin` for the vocabulary.
* **Procedures belong to their first parameter.** `formatted :: proc(r: ^Receipt)`
  is modelled as the operation `formatted` on `Receipt`, so it draws inside the
  Receipt box and `//@cdec locked` freezes it like any other method.

The tags on display:

* //@cdec no_instantiation — CheckoutService may not build domain objects.
* //@cdec factory(creates = [...]) — ReceiptFactory is the only place allowed to
  construct a Receipt.
* //@cdec immutable — a Receipt's fields never change after construction.
* //@cdec sealed — there are no specialised Receipt subtypes.
* //@cdec layer("orders") — assigns these structs to the `orders` layer.
* //@cdec locked — Receipt.formatted's implementation is frozen.
*/
package orders

import "core:fmt"

//@cdec immutable
//@cdec sealed
//@cdec layer("orders")
Receipt :: struct {
	total: f64,
	lines: int,
}

//@cdec locked(reason = "receipt wording is contractual; finance signed off on it")
formatted :: proc(r: ^Receipt) -> string {
	// FROZEN by `cdec lock` (Engine C). The digest of this body is recorded in
	// `.cdec/locks.yaml`; changing so much as the separator fails `cdec check`.
	// Try it: swap the em-dash for a comma and re-run
	//     cdec check --config examples/odin_demo --source examples/odin_demo
	// Reformat it or move the procedure up the file and nothing happens — the
	// lock is over the AST, not the text.
	return fmt.tprintf("%d line(s) — %.2f", r.lines, r.total)
}

//@cdec layer("orders")
AuditEntry :: struct {
	action: string,
}

//@cdec factory(creates = ["Receipt"])
//@cdec layer("orders")
ReceiptFactory :: struct {
	issued: int,
}

for_cart :: proc(f: ^ReceiptFactory, cart: ^Cart) -> Receipt {
	f.issued += 1
	return Receipt{total = cart_total(cart), lines = len(cart.items)} // OK: this is the factory
}

//@cdec no_instantiation(allow = ["AuditEntry"])
//@cdec layer("orders")
CheckoutService :: struct {
	receipts: ReceiptFactory,
}

summarize :: proc(s: ^CheckoutService, cart: ^Cart) -> string {
	audit := AuditEntry{action = "summarize"} // OK: whitelisted via `allow`
	receipt := for_cart(&s.receipts, cart)    // OK: a call, not a construction
	return fmt.tprintf("%s / %s", formatted(&receipt), audit.action)
}

quick_receipt :: proc(s: ^CheckoutService, cart: ^Cart) -> Receipt {
	// INTENTIONAL VIOLATION — two findings fire on the line below:
	//   [no-instantiation] 'CheckoutService.quick_receipt' constructs 'Receipt'
	//   [factory]          'Receipt' may only be built by ReceiptFactory
	// Fix by delegating:  return for_cart(&s.receipts, cart)
	return Receipt{total = cart_total(cart), lines = len(cart.items)}
}
