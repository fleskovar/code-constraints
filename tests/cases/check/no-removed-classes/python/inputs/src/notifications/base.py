class Notification:
    def send(self, message: str) -> None:
        raise NotImplementedError


class TwilioNotifier(Notification):
    """`SmsNotifier` under a new name. Matching is by qualified name, so the
    old name is gone: a removal."""

    def send(self, message: str) -> None:
        print(message)


class EmailNotifier(Notification):
    """Same class, rewritten internals. Not a removal."""

    def send(self, message: str) -> None:
        self._gateway_publish(message)

    def _gateway_publish(self, message: str) -> None:
        print(message)
