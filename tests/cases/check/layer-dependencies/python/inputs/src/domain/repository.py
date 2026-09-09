from cdec_rules import layer


@layer("domain")
class OrderRepository:
    """The port. Same layer as `Order`, so the edge between them is always
    allowed whatever the matrix says."""

    def save(self, order: "Order") -> None:
        raise NotImplementedError
