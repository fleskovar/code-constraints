namespace Orders;

// No incoming references - the DI container wires it. Exempt via
// `entry_points:`.
public class CheckoutService
{
    public Cart Cart { get; }

    public CheckoutService(Cart cart) { Cart = cart; }
}
