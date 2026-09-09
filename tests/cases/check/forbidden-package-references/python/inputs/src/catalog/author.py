from catalog.book import Book


class Author:
    """catalog -> catalog: an intra-package edge, dropped before the rule."""

    def __init__(self, name: str) -> None:
        self.name: str = name
        self.books: list[Book] = []
