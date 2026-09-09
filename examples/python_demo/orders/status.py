"""Order status enumeration."""

from enum import Enum


class OrderStatus(Enum):
    PENDING = "pending"
    PLACED = "placed"
    SHIPPED = "shipped"
    CANCELLED = "cancelled"
