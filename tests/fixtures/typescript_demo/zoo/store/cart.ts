import { Animal } from "../animals/animal";

/** Shopping cart for the store. */
export class Cart {
  static taxRate: number = 0.08;
  private items: Animal[];
  readonly currency: string = "USD";

  constructor(items: Animal[] = []) {
    this.items = items;
  }

  add(animal: Animal): void {
    this.items.push(animal);
  }

  total(): number {
    return this.items.length;
  }
}

/** Anything that can take money from a customer. */
export interface IPayment {
  charge(amount: number): boolean;
  refund(amount: number): boolean;
  readonly merchantId: string;
}

export enum Currency {
  USD,
  EUR,
  GBP,
}

export type Money = { amount: number; currency: Currency };
