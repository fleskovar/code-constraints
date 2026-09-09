from orders.factory import ReceiptFactory
from orders.receipt import Receipt


class CheckoutService:
    def __init__(self, receipts: ReceiptFactory) -> None:
        self.receipts: ReceiptFactory = receipts

    def checkout(self, total: float) -> Receipt:
        """Delegates construction. Silent."""
        return self.receipts.for_total(total)

    def quick_receipt(self, total: float) -> Receipt:
        """The violation: a shortcut around the designated factory."""
        return Receipt(total)
