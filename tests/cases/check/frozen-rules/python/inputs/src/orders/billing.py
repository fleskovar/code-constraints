from cdec_rules import immutable, no_instantiation, sealed


@immutable
class Receipt:
    """`@sealed` deleted. `@immutable` survives untouched, so only one tag
    fires here."""

    def __init__(self, total: float) -> None:
        self.total: float = round(total, 2)


@no_instantiation(allow=["AuditEntry", "Receipt"])
class CheckoutService:
    """The allow-list grew: same tag name, different params - `weakened`."""

    def subtotal(self, n: int) -> float:
        """`@no_side_effects` deleted from an *operation*."""
        return float(n)
