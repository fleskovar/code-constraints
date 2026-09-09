from notifications.base import Notification


class ExpressNotifier(Notification):
    """New in this revision, and not in `ignore:`. The violation."""

    def send(self, message: str) -> None:
        print(message)
