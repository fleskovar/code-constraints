class Notification:
    """Unchanged identity; a method was added. A CHANGED class is not an
    ADDED class, so this must stay silent."""

    def send(self, message: str) -> None:
        raise NotImplementedError

    def retry(self, attempts: int) -> None:
        raise NotImplementedError


class SmsNotifier(Notification):
    """Identical to the baseline: UNCHANGED."""

    def send(self, message: str) -> None:
        print(message)
