"""User hierarchy: abstract User with Customer / Admin specialisations."""

from abc import ABC, abstractmethod

from notifications.base import Notification


class User(ABC):
    def __init__(self, email: str, name: str) -> None:
        self.email: str = email
        self.name: str = name

    @abstractmethod
    def role(self) -> str:
        ...


class Customer(User):
    def __init__(self, email: str, name: str, notifier: Notification) -> None:
        super().__init__(email, name)
        self.notifier: Notification = notifier
        self.address: str = ""

    def role(self) -> str:
        return "customer"

    def charge(self, amount: float) -> bool:
        return amount > 0


class Admin(User):
    def __init__(self, email: str, name: str, level: int = 1) -> None:
        super().__init__(email, name)
        self.level: int = level

    def role(self) -> str:
        return "admin"
