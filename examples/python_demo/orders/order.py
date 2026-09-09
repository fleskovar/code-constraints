"""Order placement — the central sequence diagram of the demo."""

from orders.cart import Cart
from orders.status import OrderStatus


class Order:
    def __init__(self, cart: Cart) -> None:
        self.cart: Cart = cart
        self.status: OrderStatus = OrderStatus.PENDING

    def place(self) -> OrderStatus:
        # <uml-sequence name="order_place" root="self">
        result = self.cart.checkout(self.cart.total())
        if result == "ok":
            self.cart.customer.charge(self.cart.total())
            self.cart.customer.notifier.send(
                self.cart.customer.email, "Order placed"
            )
            self.status = OrderStatus.PLACED
        else:
            self.status = OrderStatus.CANCELLED
        return self.status
        # </uml-sequence>
