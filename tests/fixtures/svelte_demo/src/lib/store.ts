export interface CartItem {
  id: string;
  price: number;
}

export class Cart {
  items: CartItem[] = [];

  add(item: CartItem): void {
    this.items.push(item);
  }

  total(): number {
    return this.items.reduce((s, i) => s + i.price, 0);
  }
}
