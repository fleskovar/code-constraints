// Billing slice — a hands-on tour of the architectural-rule tags (C#).
//
// This is the part of the demo that exercises `cdec enforce` (the
// implementation-conformance engine). Every tag here is satisfied except for
// one clearly-marked, intentional violation in CheckoutService.QuickReceipt,
// so that:
//
//     cdec enforce examples/csharp_demo --lang csharp
//
// prints exactly the two findings explained inline below. Delete that method
// (or route it through the factory) and the run goes green.
//
// The five v1 tags, all on display:
//   * [NoInstantiation]        — CheckoutService may not build domain objects;
//                                it delegates construction to the factory. (headline)
//   * [Factory(Creates = ...)] — ReceiptFactory is the ONLY place allowed to
//                                construct a Receipt.
//   * [Immutable]              — a Receipt's fields never change after construction.
//   * [Sealed]                 — there are no specialised Receipt subtypes.
//   * [Layer("orders")]        — assigns these classes to the `orders` layer.
//   * [Locked]                 — Receipt.Formatted's implementation is frozen;
//                                `cdec lock check` (run by `cdec check`) fails on
//                                any change to its body.
//
// (Tag recognition only needs the `using CodeConstraints.Rules;` below; the no-op
// attribute definitions ship in `shims/csharp/CodeConstraintsRules.cs`.)

using CodeConstraints.Rules;

namespace Orders;

[Immutable]
[Sealed]
[Layer("orders")]
public class Receipt
{
    public decimal Total { get; }
    public int Lines { get; }

    public Receipt(decimal total, int lines)
    {
        Total = total;
        Lines = lines;
    }

    // FROZEN by `cdec lock` (Engine C). The digest of this body lives in
    // `.cdec/locks.yaml`; changing so much as the separator fails `cdec check`.
    // Reformat it or move it up the file and nothing happens — the lock is over
    // the syntax tree, not the text.
    [Locked(Reason = "receipt wording is contractual; finance signed off on it")]
    public string Formatted() => $"{Lines} line(s) — {Total}";  // reads only: immutable-clean
}

[Layer("orders")]
public class AuditEntry
{
    public string Action { get; }

    public AuditEntry(string action)
    {
        Action = action;
    }
}

[Factory(Creates = new[] { "Receipt" })]
[Layer("orders")]
public class ReceiptFactory
{
    // OK: this is the designated factory for Receipt.
    public Receipt ForCart(Cart cart) => new Receipt(cart.Total(), cart.Items.Count);
}

[NoInstantiation(Allow = new[] { "AuditEntry" })]
[Layer("orders")]
public class CheckoutService
{
    private readonly ReceiptFactory receipts;

    public CheckoutService(ReceiptFactory receipts)
    {
        this.receipts = receipts;
    }

    public string Summarize(Cart cart)
    {
        var audit = new AuditEntry("summarize");   // OK: whitelisted via Allow
        var receipt = receipts.ForCart(cart);      // OK: a method call, not a constructor
        return $"{receipt.Formatted()} [{audit.Action}]";
    }

    public Receipt QuickReceipt(Cart cart)
    {
        // INTENTIONAL VIOLATION — two findings fire on the line below:
        //   [no-instantiation] 'CheckoutService.QuickReceipt' constructs 'Receipt'
        //   [factory]          'Receipt' may only be built by ReceiptFactory
        // Fix by delegating:  return receipts.ForCart(cart);
        return new Receipt(cart.Total(), cart.Items.Count);
    }
}
