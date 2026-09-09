"""Authors in the bookstore catalog."""


class Author:
    def __init__(self, name: str, country: str = "Unknown") -> None:
        self.name: str = name
        self.country: str = country
        self.test_var: float = 1.0

    def display_name(self) -> str:
        return f"{self.name} ({self.country})"
