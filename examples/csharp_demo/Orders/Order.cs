using System.ComponentModel;
using CodeConstraints.Rules;

namespace Orders;

public class Order
{
    public Cart Cart { get; set; }
    public OrderStatus Status { get; set; } = OrderStatus.Pending;

    public Order(Cart cart)
    {
        Cart = cart;
    }

    // Method-level [NoInstantiation] (complements the class-level example in
    // Billing.cs). `Place` is pure orchestration — it calls existing
    // collaborators and flips an enum, but never constructs a domain object, so
    // it satisfies the rule. Add a `new Receipt(...)` here and `cdec enforce`
    // would flag it; building a whitelisted type would need `Allow = new[] {...}`.
    [NoInstantiation]
    public OrderStatus Place()
    {
        // <uml-sequence name="order_place" root="this">
        var cart_2 = new Cart();
        var result = Cart.Checkout(Cart.Total());
        if (result == "ok")
        {
            Cart.Customer.Charge(Cart.Total());
            Cart.Customer.Notifier.Send(Cart.Customer.Email, "Order placed");
            Status = OrderStatus.Placed;
        }
        else
        {
            Status = OrderStatus.Cancelled;
        }
        return Status;
        // </uml-sequence>
    }
}
