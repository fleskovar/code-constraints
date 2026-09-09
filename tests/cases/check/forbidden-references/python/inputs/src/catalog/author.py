class Author:
    """In `from:` but references nothing in `to:` - silent."""

    def __init__(self, name: str) -> None:
        self.name: str = name
