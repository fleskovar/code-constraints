from cdec_rules import layer

from domain.order import Order


@layer("application")
class CheckoutHandler:
    """application -> domain: allowed by the matrix."""

    def __init__(self, order: Order) -> None:
        self.order: Order = order
