namespace Zoo.Store;

/// <summary>
/// Shopping cart that accumulates items and totals them at checkout.
/// Lives inside a file-scoped namespace to exercise that parse path.
/// </summary>
public class Cart
{
    private double _total;
    public System.Collections.Generic.List<string> Items { get; }

    public Cart()
    {
        Items = new System.Collections.Generic.List<string>();
        _total = 0.0;
    }

    /// <summary>Add a line item to the cart.</summary>
    public void Add(string item, double price)
    {
        Items.Add(item);
        _total += price;
    }

    public string Checkout(IPayment payment)
    {
        // <uml-sequence name="checkout_flow" root="this">
        payment.Authorize(_total);
        payment.Capture();
        var receipt = FormatReceipt();
        return receipt;
        // </uml-sequence>
    }

    private string FormatReceipt()
    {
        return string.Join("\n", Items);
    }
}

/// <summary>Anything that can take money from a customer.</summary>
public interface IPayment
{
    /// <summary>Reserve <paramref name="amount"/> on the customer's account.</summary>
    void Authorize(double amount);
    void Capture();
}
