"""`cdec enforce` — implementation-conformance engine (Engine B).

Decoupled from `code_constraints.lint` (Engine A). See `engine.enforce`.
"""

from __future__ import annotations

from code_constraints.enforce.engine import enforce
from code_constraints.enforce.model import Finding, findings_to_json, format_findings

__all__ = ["enforce", "Finding", "format_findings", "findings_to_json"]
