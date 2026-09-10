"""Result types for the conformance engine (Engine B).

Deliberately separate from `code_constraints.lint.Violation`: the two engines
are decoupled by design. Engine A answers "did the architectural intent drift
over time"; Engine B answers "does the code actually obey the tag right now" by
inspecting method bodies. They share the rule *catalog* and the review-key
scheme (`code_constraints.core.keys`) so one exceptions list can cover both —
nothing else. Both are reached through rule types in `.cdec/rules.yaml`.
"""

from __future__ import annotations

from dataclasses import dataclass

from code_constraints.core.keys import make_key


@dataclass
class Finding:
    """A single conformance violation found by a body analyzer."""

    rule: str  # catalog id, e.g. "no-instantiation"
    qualified_name: str  # the element the violation is attributed to
    message: str
    file: str = ""
    line: int = 0
    # Stable discriminator between two findings of the same rule on the same
    # element — e.g. "settle->Invoice" for a construction, "rename.total" for a
    # field reassignment. Deliberately free of line numbers so the review key
    # survives edits elsewhere in the file. Every producer sets it; an empty
    # detail just means the rule can only fire once per element.
    detail: str = ""

    def fingerprint(self) -> tuple[str, str, str, int]:
        return (self.rule, self.qualified_name, self.file, self.line)

    def key(self) -> str:
        """Stable review key (`F-…`) — see `code_constraints.core.keys`."""
        return make_key("enforce", self.rule, self.qualified_name, self.detail)


def format_findings(findings: list[Finding], *, suppressed: int = 0) -> str:
    """Render findings as a human-readable report.

    Each line leads with the review key so the output can be saved, marked up,
    and fed back through `cdec exceptions patch`.
    """
    if not findings:
        text = "no conformance violations.\n"
        if suppressed:
            text += f"({suppressed} finding(s) silenced by an exception.)\n"
        return text
    lines = [f"{len(findings)} conformance violation(s):"]
    for f in sorted(findings, key=lambda x: (x.file, x.line, x.rule)):
        loc = f"{f.file}:{f.line}" if f.file else f.qualified_name
        lines.append(f"  - [{f.key()}] [{f.rule}] {loc}: {f.message}")
    if suppressed:
        lines.append(f"({suppressed} finding(s) silenced by an exception.)")
    return "\n".join(lines) + "\n"


def findings_to_json(findings: list[Finding]) -> list[dict]:
    return [
        {
            "key": f.key(),
            "rule": f.rule,
            "qualifiedName": f.qualified_name,
            "detail": f.detail,
            "message": f.message,
            "file": f.file,
            "line": f.line,
        }
        for f in findings
    ]
