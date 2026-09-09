namespace App;

using Orders;

// Also over the limit - wiring everything is its whole job. Exempt via
// `ignore:`.
public class CompositionRoot
{
    public Cart P0 { get; }
    public ReceiptFactory P1 { get; }
    public PaymentGateway P2 { get; }
    public AuditLog P3 { get; }
    public Notifier P4 { get; }
    public Inventory P5 { get; }
    public PriceTable P6 { get; }
    public ShippingCalculator P7 { get; }

    public CompositionRoot(
        Cart p0,
        ReceiptFactory p1,
        PaymentGateway p2,
        AuditLog p3,
        Notifier p4,
        Inventory p5,
        PriceTable p6,
        ShippingCalculator p7)
    {
        P0 = p0;
        P1 = p1;
        P2 = p2;
        P3 = p3;
        P4 = p4;
        P5 = p5;
        P6 = p6;
        P7 = p7;
    }
}
