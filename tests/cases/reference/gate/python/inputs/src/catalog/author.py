from catalog.book import Book


class Author:
    name: str
    rating: float

    def books(self, sort: bool) -> list[Book]:
        return []

    def retired(self) -> str:
        return "no"

    def followers(self) -> int:
        return 0
