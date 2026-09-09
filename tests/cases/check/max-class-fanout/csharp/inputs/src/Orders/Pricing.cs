namespace Orders;

// Four distinct references, with `Cart` named twice - fanout counts DISTINCT
// targets, so this is 4, not 5. Under the limit.
public class PriceCalculator
{
    public Cart Cart { get; }
    public Cart Basket { get; }
    public PriceTable Pricing { get; }

    public PriceCalculator(Cart cart, Cart basket, PriceTable pricing)
    {
        Cart = cart;
        Basket = basket;
        Pricing = pricing;
    }

    public decimal Quote(Inventory inv, ShippingCalculator ship) { return 0m; }
}
