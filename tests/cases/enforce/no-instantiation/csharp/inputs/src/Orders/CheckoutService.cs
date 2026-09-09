using CodeConstraints.Rules;

namespace Orders;

// An orchestrator: it wires collaborators together, it does not build them.
// `AuditEntry` is the one exception, declared in `Allow`.
[NoInstantiation(Allow = new[] { "AuditEntry" })]
public class CheckoutService
{
    public void Checkout(decimal total)
    {
        var entry = new AuditEntry("checkout");  // allowed by name
    }

    // The violation: `Receipt` is not in `Allow`.
    public Receipt QuickReceipt(decimal total) { return new Receipt(total); }
}
