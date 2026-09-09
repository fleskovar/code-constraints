def compute_tax(subtotal: float) -> float:
    """The rate changed. A glob-locked element is verified exactly like a
    tagged one."""
    return round(subtotal * 0.25, 2)
