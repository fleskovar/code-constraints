/** Shopping cart: holds order items belonging to a single customer. */
import { Book } from "../catalog/book";
import { Customer } from "../users/user";

export class OrderItem {
  book: Book;
  quantity: number;

  constructor(book: Book, quantity: number) {
    this.book = book;
    this.quantity = quantity;
  }

  subtotal(): number {
    return this.book.price * this.quantity;
  }
}

export class Cart {
  customer: Customer;
  items: OrderItem[];

  constructor(customer: Customer) {
    this.customer = customer;
    this.items = [];
  }

  addItem(book: Book, quantity: number = 1): boolean {
    if (book.isAvailable(quantity)) {
      const item = new OrderItem(book, quantity);
      this.items.push(item);
      return true;
    }
    return false;
  }

  total(): number {
    return this.items.reduce((s, it) => s + it.subtotal(), 0);
  }

  checkout(paymentAmount: number): string {
    if (this.items.length === 0) {
      return "empty";
    }
    if (paymentAmount < this.total()) {
      return "underpaid";
    }
    for (const item of this.items) {
      item.book.reserve(item.quantity);
    }
    return "ok";
  }
}
