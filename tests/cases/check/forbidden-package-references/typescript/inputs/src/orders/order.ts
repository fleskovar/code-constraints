import { Book } from "../catalog/book";

// orders -> catalog: the permitted direction. `from:` names catalog only.
export class Order {
  item: Book;

  constructor(item: Book) {
    this.item = item;
  }
}
