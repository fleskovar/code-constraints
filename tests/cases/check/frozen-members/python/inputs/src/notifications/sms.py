from notifications.base import Notification


class SmsNotifier(Notification):
    """Not matched by `classes:`, so its churn is invisible to this rule."""

    def send(self, message: str, urgent: bool) -> None:
        print(message, urgent)

    def preview(self) -> str:
        return "sms"
