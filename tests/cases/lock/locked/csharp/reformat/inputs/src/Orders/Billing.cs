using CodeConstraints.Rules;

namespace Orders;

public class Receipt
{
    public decimal Total { get; }
    public int Lines { get; }

    public Receipt(decimal total, int lines) { Total = total; Lines = lines; }

    // Inserted ABOVE the locked method - a lock is an AST identity, not a
    // line range.
    public void UnrelatedNewMethod() { }

    [Locked(Reason = "receipt wording is contractual; finance signed off on it")]
    public string Formatted()
    {
        // a new explanatory comment
        return $"{Lines} line(s) - total {Total}";
    }
}
