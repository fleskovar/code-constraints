from notifications.base import Notification


class EmailNotifier(Notification):
    """Matches /.*Notifier$/."""

    def send(self, message: str) -> None:
        pass
