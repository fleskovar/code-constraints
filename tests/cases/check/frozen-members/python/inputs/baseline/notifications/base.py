class Notification:
    """The published contract every downstream notifier implements."""

    def send(self, message: str) -> None:
        raise NotImplementedError

    def describe(self) -> str:
        return "notification"
