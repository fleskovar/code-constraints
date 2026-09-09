namespace Orders;

// The violation: a sealed type may not be subclassed.
public class DiscountedReceipt : Receipt
{
    public decimal Pct { get; }

    public DiscountedReceipt(decimal total, decimal pct) : base(total) { Pct = pct; }
}
