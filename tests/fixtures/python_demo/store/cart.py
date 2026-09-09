"""Sample store module with a tagged sequence diagram."""


class Cart:
    def __init__(self) -> None:
        self.items: list[str] = []
        self._total: float = 0.0

    def add(self, item: str, price: float) -> None:
        self.items.append(item)
        self._total += price

    def checkout(self, payment) -> str:
        # <uml-sequence name="checkout_flow" root="self">
        payment.authorize(self._total)
        payment.capture()
        receipt = self.format_receipt()
        return receipt
        # </uml-sequence>

    def format_receipt(self) -> str:
        return "\n".join(self.items)
