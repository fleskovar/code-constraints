import { Order } from "../orders/order";

// catalog -> orders. The forbidden edge: `Order[]` is unwrapped to `Order`.
export class Book {
  title: string;
  orders: Order[] = [];

  constructor(title: string) {
    this.title = title;
  }
}
