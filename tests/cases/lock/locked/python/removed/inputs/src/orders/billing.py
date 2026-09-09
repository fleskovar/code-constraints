class Receipt:
    """`formatted` was deleted outright. Deleting a frozen implementation is
    a mutation too, so the ledger entry has nowhere to land."""

    def __init__(self, total: float, lines: int) -> None:
        self.total: float = total
        self.lines: int = lines
