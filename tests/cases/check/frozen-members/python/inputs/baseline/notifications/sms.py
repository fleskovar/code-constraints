from notifications.base import Notification


class SmsNotifier(Notification):
    def send(self, message: str) -> None:
        print(message)
