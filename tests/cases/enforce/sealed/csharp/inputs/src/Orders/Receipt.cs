using CodeConstraints.Rules;

namespace Orders;

// A value object whose invariants cannot survive being extended.
[Sealed]
public class Receipt
{
    public decimal Total { get; }

    public Receipt(decimal total) { Total = total; }
}
