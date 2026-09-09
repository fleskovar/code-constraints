from catalog.book import Book


class Order:
    """orders -> catalog: the permitted direction."""

    def __init__(self, book: Book) -> None:
        self.book: Book = book
