from cdec_rules import layer

from domain.repository import OrderRepository


@layer("infrastructure")
class SqlConnection:
    def execute(self, sql: str) -> None:
        pass


@layer("infrastructure")
class SqlOrderRepository(OrderRepository):
    """infrastructure -> domain: explicitly allowed. Dependency inversion
    done right."""

    def save(self, order: "Order") -> None:
        pass
