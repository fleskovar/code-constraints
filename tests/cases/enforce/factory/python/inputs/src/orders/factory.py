from cdec_rules import factory

from orders.receipt import Receipt


@factory(creates=["Receipt"])
class ReceiptFactory:
    """The designated constructor. Construction is permitted anywhere inside
    the owning class, so this is silent."""

    def for_total(self, total: float) -> Receipt:
        return Receipt(total)
