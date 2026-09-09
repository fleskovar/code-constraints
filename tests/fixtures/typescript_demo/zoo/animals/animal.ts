/** Abstract base class for every living creature in the menagerie. */
export abstract class Animal {
  name: string;
  protected legs: number;

  constructor(name: string, legs: number = 4) {
    this.name = name;
    this.legs = legs;
  }

  /** Return the sound this animal makes. */
  abstract speak(): string;
}

export class Dog extends Animal {
  breed: string;

  constructor(name: string) {
    super(name, 4);
    this.breed = "mixed";
  }

  speak(): string {
    if (this.breed === "mixed") {
      return "Woof";
    } else {
      return "Bark";
    }
  }
}
