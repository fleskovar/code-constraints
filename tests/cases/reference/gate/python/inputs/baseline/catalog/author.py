from catalog.book import Book


class Author:
    name: str
    rating: int

    def books(self) -> list[Book]:
        return []

    def retired(self) -> bool:
        return False
