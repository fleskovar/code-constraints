class AuditEntry:
    """`@sealed` deleted here too - but `support.**` is outside the
    `classes:` glob, so this rule never looks."""

    def __init__(self, action: str) -> None:
        self.action: str = action
