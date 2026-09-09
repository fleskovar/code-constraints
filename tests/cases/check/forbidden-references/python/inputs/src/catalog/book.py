from users.customer import Customer


class Book:
    """The violation: a `users.Customer` parameter type."""

    def __init__(self, title: str, reserved_by: Customer) -> None:
        self.title: str = title
        self.reserved_by: Customer = reserved_by
