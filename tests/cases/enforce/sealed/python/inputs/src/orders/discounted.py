from orders.receipt import Receipt


class DiscountedReceipt(Receipt):
    """The violation: a sealed type may not be subclassed."""

    def __init__(self, total: float, pct: float) -> None:
        super().__init__(total)
        self.pct: float = pct
