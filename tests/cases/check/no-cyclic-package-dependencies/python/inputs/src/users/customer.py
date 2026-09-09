from orders.order import Order


class Customer:
    """users -> orders."""

    def __init__(self, latest: Order) -> None:
        self.latest: Order = latest
