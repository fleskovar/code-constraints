"""Notification senders. Abstract base + two concrete channels."""

from abc import ABC, abstractmethod


class Notification(ABC):
    def __init__(self, sender: str) -> None:
        self.sender: str = sender

    @abstractmethod
    def send(self, to: str, message: str) -> bool:
        ...


class EmailNotifier(Notification):
    def __init__(self, sender: str = "noreply@bookstore.com") -> None:
        super().__init__(sender)
        self.smtp_host: str = "localhost"

    def send(self, to: str, message: str) -> bool:
        return "@" in to


class SmsNotifier(Notification):
    def __init__(self, sender: str = "12345") -> None:
        super().__init__(sender)
        self.short_code: str = sender

    def send(self, to: str, message: str) -> bool:
        return len(message) <= 160
