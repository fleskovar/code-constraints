"""Implementation-conformance engine (Engine B).

Answers "does the code actually obey the constraint tags written on it" by
re-parsing the source and inspecting method bodies. Driven by the
`tag-conformance` rule type in `.cdec/rules.yaml`, which is what `cdec check`
runs; this package stays decoupled from `code_constraints.lint`, and the rule
is a thin adapter over `engine.enforce`.
"""

from __future__ import annotations

from code_constraints.enforce.engine import enforce
from code_constraints.enforce.model import Finding, findings_to_json, format_findings

__all__ = ["enforce", "Finding", "format_findings", "findings_to_json"]
