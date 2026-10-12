from notifications.base import Notifier


class Registry(type):
    """New. `type` is not an approved base. One violation."""


class PushNotifier(Notifier, metaclass=Registry):
    """New. The base is approved, but it sets a metaclass. One violation."""

    def send(self, message: str) -> None:
        print(message)
