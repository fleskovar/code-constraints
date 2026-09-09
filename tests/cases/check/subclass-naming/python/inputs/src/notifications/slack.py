from notifications.base import Notification


class SlackHook(Notification):
    """The violation: inherits the base, name does not match the pattern."""

    def send(self, message: str) -> None:
        pass
