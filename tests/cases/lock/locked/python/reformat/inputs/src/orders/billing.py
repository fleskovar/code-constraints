from cdec_rules import locked


class Receipt:
    """A brand new class docstring, which is not part of the locked body."""

    def __init__(self, total: float, lines: int) -> None:
        self.total: float = total
        self.lines: int = lines

    def unrelated_new_method(self) -> None:
        """Inserted ABOVE the locked method - a lock is an AST identity,
        not a line range."""

    @locked(reason="receipt wording is contractual; finance signed off on it")
    def formatted(
        self,
    ) -> str:
        # a new explanatory comment
        return f"{self.lines} line(s) - total {self.total:.2f}"
