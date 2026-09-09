from users.customer import Customer


class Order:
    """References the forbidden *target*, but is not in `from:` - silent.
    The rule is directional."""

    def __init__(self, customer: Customer) -> None:
        self.customer: Customer = customer
