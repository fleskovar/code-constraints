class Notification:
    """The published contract. Present in the baseline."""

    def send(self, message: str) -> None:
        raise NotImplementedError


class SmsNotifier(Notification):
    """Present in the baseline."""

    def send(self, message: str) -> None:
        print(message)
