from cdec_rules import locked


class Receipt:
    def __init__(self, total: float, lines: int) -> None:
        self.total: float = total
        self.lines: int = lines

    @locked(reason="receipt wording is contractual; finance signed off on it")
    def formatted(self) -> str:
        return f"{self.lines} item(s) - total {self.total:.2f}"
