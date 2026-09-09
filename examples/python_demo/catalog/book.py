"""Books — each book has one author and lives in the catalog."""

from catalog.author import Author


class Book:
    def __init__(
        self,
        title: str,
        author: Author,
        price: float,
        stock: int = 0,
    ) -> None:
        self.title: str = title
        self.author: Author = author
        self.price: float = price
        self.stock: int = stock

    def is_available(self, requested: int = 1) -> bool:
        # <uml-activity name="book_availability" granularity="statement">
        in_stock = self.stock >= requested
        priced = self.price > 0
        result = in_stock and priced
        return result
        # </uml-activity>

    def reserve(self, quantity: int) -> None:
        self.stock -= quantity
