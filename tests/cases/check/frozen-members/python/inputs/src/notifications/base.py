class Notification:
    """`send` gained a parameter; `describe` is untouched; a private
    attribute appeared."""

    _retries: int = 3

    def send(self, message: str, urgent: bool) -> None:
        raise NotImplementedError

    def describe(self) -> str:
        return "notification"
