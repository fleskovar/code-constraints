"""Billing slice — a hands-on tour of the architectural-rule tags.

This is the part of the demo that exercises **`cdec enforce`** (the
implementation-conformance engine). Every tag here is *satisfied* except for
one clearly-marked, intentional violation in `CheckoutService.quick_receipt`,
so that:

    cdec enforce examples/python_demo --lang python

prints exactly the two findings explained inline below. Delete that method (or
route it through the factory) and the run goes green.

The five v1 tags, all on display:

* ``@no_instantiation`` — `CheckoutService` may not build domain objects; it
  delegates construction to the factory. (headline example)
* ``@factory(creates=[...])`` — `ReceiptFactory` is the *only* place allowed to
  construct a `Receipt`.
* ``@immutable`` — a `Receipt`'s fields never change after construction.
* ``@sealed`` — there are no specialised `Receipt` subtypes.
* ``@layer("orders")`` — assigns these classes to the ``orders`` layer (used by
  the ``layer-dependencies`` rule and shown as a badge in the web viewer).
* ``@locked`` — `Receipt.formatted`'s implementation is frozen; `cdec lock check`
  (run automatically by `cdec check`) fails on any change to its body.
"""

from cdec_rules import factory, immutable, layer, locked, no_instantiation, sealed

from orders.cart import Cart


@immutable
@sealed
@layer("orders")
class Receipt:
    """A finalised receipt: built once, never mutated, never subclassed."""

    def __init__(self, total: float, lines: int) -> None:
        self.total: float = total
        self.lines: int = lines

    @locked(reason="receipt wording is contractual; finance signed off on it")
    def formatted(self) -> str:
        # FROZEN by `cdec lock` (Engine C). The digest of this body is recorded in
        # `.cdec/locks.yaml`; changing so much as the separator fails `cdec check`.
        # Try it: swap the em-dash for a comma and re-run
        #     cdec check --config examples/python_demo --source examples/python_demo
        # Reformat it or move the method up the file and nothing happens — the
        # lock is over the AST, not the text.
        return f"{self.lines} line(s) — {self.total:.2f}"  # reads only: immutable-clean


@layer("orders")
class AuditEntry:
    """A lightweight bookkeeping record. It is *not* factory-controlled, so
    services may build it directly — which is why `CheckoutService` lists it in
    its ``allow``."""

    def __init__(self, action: str) -> None:
        self.action: str = action


@factory(creates=["Receipt"])
@layer("orders")
class ReceiptFactory:
    """The designated constructor of `Receipt`. Building a `Receipt` anywhere
    else is a ``factory`` violation."""

    def for_cart(self, cart: Cart) -> Receipt:
        return Receipt(cart.total(), len(cart.items))  # OK: this is the factory


@no_instantiation(allow=["AuditEntry"])
@layer("orders")
class CheckoutService:
    """Coordinates an existing cart and the receipt factory.

    Tagged ``@no_instantiation`` because a service should orchestrate, not
    construct: it delegates `Receipt` creation to `ReceiptFactory`.
    ``allow=["AuditEntry"]`` carves out the one bookkeeping type it may still
    build directly.
    """

    def __init__(self, receipts: ReceiptFactory) -> None:
        self.receipts: ReceiptFactory = receipts

    def summarize(self, cart: Cart) -> dict:
        audit = AuditEntry("summarize")          # OK: whitelisted via `allow`
        receipt = self.receipts.for_cart(cart)   # OK: a method call, not a constructor
        return {"summary": receipt.formatted(), "audit": audit.action}

    def quick_receipt(self, cart: Cart) -> Receipt:
        # INTENTIONAL VIOLATION — two findings fire on the line below:
        #   [no-instantiation] 'CheckoutService.quick_receipt' constructs 'Receipt'
        #   [factory]          'Receipt' may only be built by ReceiptFactory
        # Fix by delegating:  return self.receipts.for_cart(cart)
        return Receipt(cart.total(), len(cart.items))
