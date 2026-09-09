"""`cdec reference` — architecture-reference gate.

A dedicated structural comparator (decoupled from `code_constraints.core.diff` and from the
`code_constraints.lint` / `code_constraints.enforce` engines) that fails when the current code deviates in
any structural way from a stored reference XMI snapshot. Used by `cdec reference
test` as a CI gate.
"""

from __future__ import annotations

from code_constraints.reference.compare import Deviation, compare_to_reference
from code_constraints.reference.report import format_human, to_json

__all__ = ["Deviation", "compare_to_reference", "format_human", "to_json"]
