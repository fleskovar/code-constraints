from orders.collaborators import Cart, Inventory, PriceTable, ShippingCalculator


class PriceCalculator:
    """Four distinct references, and `Cart` twice - fanout counts DISTINCT
    targets, so this is 4, not 5. Under the limit."""

    def __init__(self, cart: Cart, basket: Cart, pricing: PriceTable) -> None:
        self.cart: Cart = cart
        self.basket: Cart = basket
        self.pricing: PriceTable = pricing

    def quote(self, inv: Inventory, ship: ShippingCalculator) -> float:
        return 0.0
