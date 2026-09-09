export class Book {
  title: string;
  rating: number;

  constructor(title: string) {
    this.title = title;
    this.rating = 0;
  }

  pages(): number {
    return 0;
  }
}
