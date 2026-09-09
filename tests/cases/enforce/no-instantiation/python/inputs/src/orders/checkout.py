from cdec_rules import no_instantiation

from orders.models import AuditEntry, Receipt


@no_instantiation(allow=["AuditEntry"])
class CheckoutService:
    """An orchestrator: it wires collaborators together, it does not build
    them. `AuditEntry` is the one exception, declared in `allow`."""

    def checkout(self, total: float) -> None:
        entry = AuditEntry("checkout")  # allowed by name
        print(entry.action)

    def quick_receipt(self, total: float) -> Receipt:
        """The violation: `Receipt` is not in `allow`."""
        return Receipt(total)
