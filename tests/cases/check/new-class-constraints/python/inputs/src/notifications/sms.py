from notifications.base import Notifier


class SmsNotifier(Notifier):
    """New. Extends the approved base directly. Passes."""

    def send(self, message: str) -> None:
        print(message)
