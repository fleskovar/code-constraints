from notifications.base import Notification


class FakeNotifier(Notification):
    """Also new, but `testing.**` is in `ignore:` — exempt."""

    def send(self, message: str) -> None:
        pass
