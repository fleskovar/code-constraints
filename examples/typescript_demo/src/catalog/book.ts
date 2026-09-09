/** Books — each book has one author and lives in the catalog. */
import { Author } from "./author";

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

  isAvailable(requested: number = 1): boolean {
    const inStock = this.stock >= requested;
    const priced = this.price > 0;
    return inStock && priced;
  }

  reserve(quantity: number): void {
    this.stock -= quantity;
  }
}
