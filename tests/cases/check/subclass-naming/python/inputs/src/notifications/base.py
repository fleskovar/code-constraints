class Notification:
    """The base itself does not inherit from `Notification`, so the rule
    never examines its name."""

    def send(self, message: str) -> None:
        raise NotImplementedError
