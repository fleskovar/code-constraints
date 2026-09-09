class Book:
    """A leaf: referenced by orders, references nobody. It cannot be in a
    cycle, so it never appears in the output."""

    def __init__(self, title: str) -> None:
        self.title: str = title
