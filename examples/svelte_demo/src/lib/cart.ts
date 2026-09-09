/** Cart model used by `CartView.svelte`. */
import { Book } from "./catalog";

export interface CartLine {
  book: Book;
  quantity: number;
}

export class Cart {
  lines: CartLine[] = [];

  add(book: Book, quantity: number = 1): boolean {
    if (!book.isAvailable(quantity)) return false;
    const existing = this.lines.find((l) => l.book.title === book.title);
    if (existing) {
      existing.quantity += quantity;
    } else {
      this.lines.push({ book, quantity });
    }
    return true;
  }

  remove(title: string): void {
    this.lines = this.lines.filter((l) => l.book.title !== title);
  }

  total(): number {
    return this.lines.reduce((s, l) => s + l.book.price * l.quantity, 0);
  }
}
