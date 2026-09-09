"""Fixture exercising every v1 architectural-rule tag (Python)."""

from cdec_rules import factory, immutable, layer, no_instantiation, sealed


@layer("domain")
@sealed
class Repository:
    """A sealed domain class."""

    def find(self, key: int):
        return None


class SpecialRepository(Repository):  # sealed VIOLATION: subclasses a @sealed class
    pass


@immutable
class Money:
    def __init__(self, amount: int):
        self.amount = amount

    def add(self, other: int) -> int:
        return self.amount + other  # clean: reads only

    def reset(self) -> None:
        self.amount = 0  # immutable VIOLATION: reassigns a field outside __init__


class OrderService:
    @no_instantiation
    def total(self, items: list) -> int:
        return sum(items)  # clean: no construction

    @no_instantiation(allow=["list"])
    def collect(self):
        acc = list()  # allowed by `allow`
        return acc


@factory(creates=["Repository"])
class RepositoryFactory:
    def create(self) -> Repository:
        return Repository()  # allowed: this is the designated factory


class Sneaky:
    def make(self):
        return Repository()  # factory VIOLATION: constructs Repository outside the factory
