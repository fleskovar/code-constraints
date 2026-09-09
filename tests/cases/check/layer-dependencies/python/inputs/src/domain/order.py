from cdec_rules import layer

from infrastructure.sql import SqlConnection
from support.logger import Logger


@layer("domain")
class Order:
    """The violation: `domain` allows nothing, and SqlConnection is
    `infrastructure`. The `Logger` reference is invisible - its class carries
    no `@layer` tag, and the rule cannot reason about untagged targets."""

    def __init__(self, conn: SqlConnection, log: Logger) -> None:
        self.conn: SqlConnection = conn
        self.log: Logger = log
