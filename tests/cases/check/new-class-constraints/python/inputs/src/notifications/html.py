from notifications.base import EmailNotifier


class HtmlEmailNotifier(EmailNotifier):
    """New. Reaches Notifier through EmailNotifier. Passes."""

    def send(self, message: str) -> None:
        print(f"<p>{message}</p>")
