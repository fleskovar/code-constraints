"""The architecture-reference gate.

A dedicated structural comparator (decoupled from `code_constraints.core.diff`
and from the `code_constraints.lint` / `code_constraints.enforce` engines) that
reports every structural deviation of the current code from a stored reference
model. Driven by the `reference-architecture` rule type in `.cdec/rules.yaml`,
which is what `cdec check` runs.
"""

from __future__ import annotations

from code_constraints.reference.compare import Deviation, compare_to_reference
from code_constraints.reference.report import format_human, to_json

__all__ = ["Deviation", "compare_to_reference", "format_human", "to_json"]
