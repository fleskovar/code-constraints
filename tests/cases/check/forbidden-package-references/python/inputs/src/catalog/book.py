from orders.order import Order


class Book:
    """catalog -> orders: the forbidden edge. `list[Order]` unwraps to Order."""

    def __init__(self, title: str) -> None:
        self.title: str = title
        self.orders: list[Order] = []
