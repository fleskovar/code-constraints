namespace Orders;

public class CheckoutService
{
    private readonly ReceiptFactory _receipts;

    public CheckoutService(ReceiptFactory receipts) { _receipts = receipts; }

    // Delegates construction. Silent.
    public Receipt Checkout(decimal total) { return _receipts.ForTotal(total); }

    // The violation: a shortcut around the designated factory.
    public Receipt QuickReceipt(decimal total) { return new Receipt(total); }
}
