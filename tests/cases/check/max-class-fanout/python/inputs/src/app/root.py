from orders.collaborators import (
    AuditLog,
    Cart,
    Inventory,
    Notifier,
    PaymentGateway,
    PriceTable,
    ReceiptFactory,
    ShippingCalculator,
)


class CompositionRoot:
    """Also over the limit - wiring everything is its whole job. Exempt via
    `ignore:`."""

    def __init__(
        self,
        cart: Cart,
        receipts: ReceiptFactory,
        payments: PaymentGateway,
        audit: AuditLog,
        notifier: Notifier,
        inventory: Inventory,
        pricing: PriceTable,
        shipping: ShippingCalculator,
    ) -> None:
        self.cart: Cart = cart
        self.receipts: ReceiptFactory = receipts
        self.payments: PaymentGateway = payments
        self.audit: AuditLog = audit
        self.notifier: Notifier = notifier
        self.inventory: Inventory = inventory
        self.pricing: PriceTable = pricing
        self.shipping: ShippingCalculator = shipping
