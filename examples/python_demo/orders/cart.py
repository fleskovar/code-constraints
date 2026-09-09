"""Shopping cart: holds order items belonging to a single customer.

`Cart.checkout` is tagged as a control-flow activity diagram so the canvas
renders decision/merge nodes for the validation steps.

`Cart.add_item` is tagged as a sequence diagram — it interacts with `Book` to
check availability before appending.
"""

from catalog.book import Book
from users.user import Customer


class OrderItem:
    def __init__(self, book: Book, quantity: int) -> None:
        self.book: Book = book
        self.quantity: int = quantity

    def subtotal(self) -> float:
        return self.book.price * self.quantity


class Cart:
    def __init__(self, customer: Customer) -> None:
        self.customer: Customer = customer
        self.items: list[OrderItem] = []

    def add_item(self, book: Book, quantity: int = 1) -> bool:
        # <uml-sequence name="cart_add_item" root="self">
        if book.is_available(quantity):
            item = OrderItem(book, quantity)
            self.items.append(item)
            return True
        return False
        # </uml-sequence>

    def total(self) -> float:
        return sum(it.subtotal() for it in self.items)

    def checkout(self, payment_amount: float) -> str:
        # <uml-activity name="cart_checkout" granularity="control-flow">
        if not self.items:
            return "empty"
        if payment_amount < self.total():
            return "underpaid"
        for item in self.items:
            item.book.reserve(item.quantity)
        return "ok"
        # </uml-activity>
