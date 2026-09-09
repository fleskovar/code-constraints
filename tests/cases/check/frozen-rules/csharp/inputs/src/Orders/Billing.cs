using CodeConstraints.Rules;

namespace Orders;

// [Sealed] deleted. [Immutable] survives untouched.
[Immutable]
public class Receipt
{
    public decimal Total { get; }

    public Receipt(decimal total) { Total = decimal.Round(total, 2); }
}

// The allow-list grew: same tag, different params - `weakened`.
[NoInstantiation(Allow = new[] { "AuditEntry", "Receipt" })]
public class CheckoutService
{
    // [NoSideEffects] deleted from an *operation*.
    public decimal Subtotal(int n) { return n; }
}
