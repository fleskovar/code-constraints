"""Sample animals module for parser tests."""

from abc import ABC, abstractmethod


class Animal(ABC):
    """Abstract base class for every living creature in the menagerie."""

    species: str = "unknown"

    def __init__(self, name: str, legs: int = 4) -> None:
        self.name: str = name
        self.legs: int = legs

    @abstractmethod
    def speak(self) -> str:
        """Return the sound this animal makes."""
        ...

    def describe(self) -> str:
        return f"{self.name} ({self.species})"


class Dog(Animal):
    def __init__(self, name: str) -> None:
        super().__init__(name=name, legs=4)
        self.breed: str = "mixed"

    def speak(self) -> str:
        # <uml-activity name="dog_speak" granularity="control-flow">
        if self.breed == "mixed":
            return "Woof"
        elif self.breed == "wolf":
            return "Howl"
        else:
            return "Bark"
        # </uml-activity>
