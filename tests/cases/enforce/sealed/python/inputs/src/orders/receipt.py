from cdec_rules import sealed


@sealed
class Receipt:
    """A value object whose invariants cannot survive being extended."""

    def __init__(self, total: float) -> None:
        self.total: float = total
