export interface CartItem {
  id: string;
  price: number;
}

// Referenced by the CartView component.
export class Cart {
  items: CartItem[] = [];

  total(): number {
    return this.items.reduce((s, i) => s + i.price, 0);
  }
}
