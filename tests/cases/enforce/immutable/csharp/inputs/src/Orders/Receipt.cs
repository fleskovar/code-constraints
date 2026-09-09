using CodeConstraints.Rules;

namespace Orders;

[Immutable]
public class Receipt
{
    private decimal _total;
    private int _lines;

    // Constructor assignment is initialisation, not mutation.
    public Receipt(decimal total, int lines)
    {
        _total = total;
        _lines = lines;
    }

    // Returns a new instance instead of mutating. Silent.
    public Receipt WithDiscount(decimal pct)
    {
        return new Receipt(_total * (1 - pct), _lines);
    }

    // Reads only. Silent.
    public string Formatted() { return $"{_lines} line(s)"; }

    // The violation: reassigns a field outside the constructor.
    public void ApplyDiscount(decimal pct)
    {
        _total = _total * (1 - pct);
    }
}
