from notifications.base import Notification


class LegacyPager(Notification):
    """Also breaks the pattern, but it is named in `ignore:`."""

    def send(self, message: str) -> None:
        pass
