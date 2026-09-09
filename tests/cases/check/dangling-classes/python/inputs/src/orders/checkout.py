from orders.cart import Cart


class CheckoutService:
    """No incoming references at all - the DI container wires it. Exempt
    because it is named in `entry_points:`."""

    def __init__(self, cart: Cart) -> None:
        self.cart: Cart = cart
