using CodeConstraints.Rules;

namespace Orders;

// The designated constructor. Construction is permitted anywhere inside the
// owning class, so this is silent.
[Factory(Creates = new[] { "Receipt" })]
public class ReceiptFactory
{
    public Receipt ForTotal(decimal total)
    {
        return new Receipt(total);
    }
}
