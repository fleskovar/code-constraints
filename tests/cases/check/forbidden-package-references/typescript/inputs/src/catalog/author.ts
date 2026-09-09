import { Book } from "./book";

// catalog -> catalog. A self-edge is dropped before the rule sees it.
export class Author {
  name: string;
  books: Book[] = [];

  constructor(name: string) {
    this.name = name;
  }
}
