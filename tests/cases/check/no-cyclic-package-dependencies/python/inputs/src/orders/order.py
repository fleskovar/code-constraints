from catalog.book import Book
from users.customer import Customer


class Order:
    """orders -> users (closing the cycle) and orders -> catalog (acyclic)."""

    def __init__(self, customer: Customer, book: Book) -> None:
        self.customer: Customer = customer
        self.book: Book = book
