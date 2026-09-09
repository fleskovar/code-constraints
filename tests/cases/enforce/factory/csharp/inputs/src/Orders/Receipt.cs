namespace Orders;

public class Receipt
{
    public decimal Total { get; }

    public Receipt(decimal total) { Total = total; }
}
