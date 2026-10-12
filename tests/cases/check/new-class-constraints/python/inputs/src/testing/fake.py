class FakeNotifier:
    """New, with no approved base, but `testing.**` is in `ignore:`."""

    def send(self, message: str) -> None:
        pass
