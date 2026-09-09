using CodeConstraints.Rules;

namespace Orders;

public class Receipt
{
    public decimal Total { get; }
    public int Lines { get; }

    public Receipt(decimal total, int lines) { Total = total; Lines = lines; }

    [Locked(Reason = "receipt wording is contractual; finance signed off on it")]
    public string Formatted() { return $"{Lines} line(s) - total {Total}"; }
}
