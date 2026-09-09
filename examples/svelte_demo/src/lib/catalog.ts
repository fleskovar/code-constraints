/** Bookstore domain types shared by the Svelte components. */

export class Author {
  name: string;
  country: string;

  constructor(name: string, country: string = "Unknown") {
    this.name = name;
    this.country = country;
  }
}

export class Book {
  title: string;
  author: Author;
  price: number;
  stock: number;

  constructor(title: string, author: Author, price: number, stock: number = 0) {
    this.title = title;
    this.author = author;
    this.price = price;
    this.stock = stock;
  }

  isAvailable(quantity: number = 1): boolean {
    return this.stock >= quantity && this.price > 0;
  }
}
