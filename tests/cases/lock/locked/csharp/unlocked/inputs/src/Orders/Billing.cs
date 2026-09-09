using CodeConstraints.Rules;

namespace Orders;

public class Receipt
{
    public decimal Total { get; }
    public int Lines { get; }

    public Receipt(decimal total, int lines) { Total = total; Lines = lines; }

    public string Formatted() { return $"{Lines} line(s) - total {Total}"; }
}
