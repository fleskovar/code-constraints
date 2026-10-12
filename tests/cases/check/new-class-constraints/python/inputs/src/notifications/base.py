class Notifier:
    """The approved building block."""

    def send(self, message: str) -> None:
        raise NotImplementedError


class EmailNotifier(Notifier):
    def send(self, message: str) -> None:
        print(message)


class LegacyQueue:
    """No approved base. It is in the baseline, so it is not new."""

    def push(self, message: str) -> None:
        print(message)
