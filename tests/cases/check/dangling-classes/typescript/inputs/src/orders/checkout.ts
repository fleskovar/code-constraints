import { Cart } from "./cart";

// No incoming references - the composition root wires it. Exempt because it
// is named in `entry_points:`.
export class CheckoutService {
  cart: Cart;

  constructor(cart: Cart) {
    this.cart = cart;
  }
}
