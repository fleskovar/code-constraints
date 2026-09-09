class Customer:
    """In `to:` but never referenced from catalog."""

    def __init__(self, email: str) -> None:
        self.email: str = email
