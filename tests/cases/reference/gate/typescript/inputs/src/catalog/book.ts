export abstract class Book {
  title: string;
  isbn: string;

  constructor(title: string) {
    this.title = title;
    this.isbn = "";
  }

  pages(hardback: boolean): number {
    return 0;
  }
}

export class Series {
  name: string = "";
}
