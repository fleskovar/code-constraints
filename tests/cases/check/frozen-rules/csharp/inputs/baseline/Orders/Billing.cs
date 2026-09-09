using CodeConstraints.Rules;

namespace Orders;

[Immutable]
[Sealed]
public class Receipt
{
    public decimal Total { get; }

    public Receipt(decimal total) { Total = total; }
}

[NoInstantiation(Allow = new[] { "AuditEntry" })]
public class CheckoutService
{
    [NoSideEffects]
    public decimal Subtotal(int n) { return n; }
}
