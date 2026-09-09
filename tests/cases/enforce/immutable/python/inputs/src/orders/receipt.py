from cdec_rules import immutable


@immutable
class Receipt:
    def __init__(self, total: float, lines: int) -> None:
        # Constructor assignment is initialisation, not mutation.
        self.total: float = total
        self.lines: int = lines

    def with_discount(self, pct: float) -> "Receipt":
        """A 'modification' that returns a new instance. No assignment to
        `self`, so nothing fires."""
        return Receipt(self.total * (1 - pct), self.lines)

    def formatted(self) -> str:
        """Reads only."""
        return f"{self.lines} line(s)"

    def apply_discount(self, pct: float) -> None:
        """The violation: reassigns a field outside `__init__`."""
        self.total *= 1 - pct
