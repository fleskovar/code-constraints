class Book:
    """Internals rewritten, public shape identical. Silent."""

    def __init__(self, title: str) -> None:
        self.title: str = title.strip()
