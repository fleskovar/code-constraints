"""Human + JSON formatting for reference-gate deviations."""

from __future__ import annotations

from code_constraints.reference.compare import Deviation


def format_human(deviations: list[Deviation]) -> str:
    """Render deviations as a readable, CI-friendly report, grouped by class."""
    if not deviations:
        return "cdec reference test: no deviations -- the codebase matches the reference.\n"

    lines = [
        f"cdec reference test: {len(deviations)} deviation(s) from the reference:",
    ]
    current_qn: str | None = None
    for d in sorted(deviations, key=Deviation.sort_key):
        if d.qualified_name != current_qn:
            current_qn = d.qualified_name
            lines.append(f"\n  {current_qn}")
        lines.append(f"    - [{d.category}] {d.message}")
    return "\n".join(lines) + "\n"


def to_json(deviations: list[Deviation]) -> dict:
    """Machine-readable report for pipelines."""
    return {
        "deviation_count": len(deviations),
        "deviations": [
            {
                "category": d.category,
                "qualifiedName": d.qualified_name,
                "member": d.member,
                "message": d.message,
                "old": d.old,
                "new": d.new,
            }
            for d in sorted(deviations, key=Deviation.sort_key)
        ],
    }
