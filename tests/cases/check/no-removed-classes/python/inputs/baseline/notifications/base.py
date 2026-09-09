class Notification:
    def send(self, message: str) -> None:
        raise NotImplementedError


class SmsNotifier(Notification):
    """Renamed in the current revision."""

    def send(self, message: str) -> None:
        print(message)


class EmailNotifier(Notification):
    def send(self, message: str) -> None:
        print(message)
