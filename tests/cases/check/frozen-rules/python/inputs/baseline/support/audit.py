from cdec_rules import sealed


@sealed
class AuditEntry:
    def __init__(self, action: str) -> None:
        self.action: str = action
