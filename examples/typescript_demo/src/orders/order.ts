/** Order placement — ties together cart, customer, and notification. */
import { Cart } from "./cart";
import { OrderStatus } from "./status";

export class Order {
  cart: Cart;
  status: OrderStatus;

  constructor(cart: Cart) {
    this.cart = cart;
    this.status = OrderStatus.PENDING;
  }

  place(): OrderStatus {
    const result = this.cart.checkout(this.cart.total());
    if (result === "ok") {
      this.cart.customer.charge(this.cart.total());
      this.cart.customer.notifier.send(
        this.cart.customer.email,
        "Order placed",
      );
      this.status = OrderStatus.PLACED;
    } else {
      this.status = OrderStatus.CANCELLED;
    }
    return this.status;
  }
}
