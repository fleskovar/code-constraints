def compute_tax(subtotal: float) -> float:
    """No `@locked` tag anywhere - this module is frozen by a
    `lock.targets:` glob in `.cdec/config.yaml` instead."""
    return round(subtotal * 0.2, 2)
