/** Authors in the bookstore catalog. */
export class Author {
  name: string;
  country: string;

  constructor(name: string, country: string = "Unknown") {
    this.name = name;
    this.country = country;
  }

  displayName(): string {
    return `${this.name} (${this.country})`;
  }
}
