from cdec_rules import immutable, no_instantiation, no_side_effects, sealed


@immutable
@sealed
class Receipt:
    def __init__(self, total: float) -> None:
        self.total: float = total


@no_instantiation(allow=["AuditEntry"])
class CheckoutService:
    @no_side_effects
    def subtotal(self, n: int) -> float:
        return float(n)
