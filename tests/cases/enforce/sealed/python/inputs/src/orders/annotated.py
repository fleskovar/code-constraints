from orders.receipt import Receipt


class AnnotatedReceipt:
    """Composition instead of inheritance: holds a Receipt, does not extend
    it. This is the sanctioned way to add behaviour to a sealed type."""

    def __init__(self, receipt: Receipt, note: str) -> None:
        self.receipt: Receipt = receipt
        self.note: str = note
