namespace Orders;

public class Receipt
{
    public decimal Total { get; }

    public Receipt(decimal total) { Total = total; }
}

public class AuditEntry
{
    public string Action { get; }

    public AuditEntry(string action) { Action = action; }
}
