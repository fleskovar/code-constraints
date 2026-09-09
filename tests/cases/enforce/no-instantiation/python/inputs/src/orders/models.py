class Receipt:
    def __init__(self, total: float) -> None:
        self.total: float = total


class AuditEntry:
    def __init__(self, action: str) -> None:
        self.action: str = action
