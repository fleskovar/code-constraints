namespace Orders;

// Composition instead of inheritance: holds a Receipt, does not extend it.
public class AnnotatedReceipt
{
    public Receipt Receipt { get; }
    public string Note { get; }

    public AnnotatedReceipt(Receipt receipt, string note)
    {
        Receipt = receipt;
        Note = note;
    }
}
