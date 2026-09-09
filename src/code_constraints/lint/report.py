"""Format the linter output as human-readable text or JSON."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from code_constraints.lint.rules.base import Severity, Violation


@dataclass
class Report:
    violations: list[Violation] = field(default_factory=list)
    suppressed: list[Violation] = field(default_factory=list)
    # Rules that the engine couldn't run (e.g. diff-rule with no baseline).
    skipped: list[tuple[str, str]] = field(default_factory=list)

    def has_failures(self, fail_on: Severity) -> bool:
        if fail_on == Severity.OFF:
            return False
        if fail_on == Severity.WARNING:
            return any(v.severity in (Severity.ERROR, Severity.WARNING) for v in self.violations)
        # default: error
        return any(v.severity == Severity.ERROR for v in self.violations)

    def to_human(self) -> str:
        if not self.violations and not self.skipped:
            return "cdec check: no violations.\n"
        lines: list[str] = []
        # Group by rule id for compact output.
        by_rule: dict[str, list[Violation]] = {}
        for v in self.violations:
            by_rule.setdefault(v.rule_id, []).append(v)
        for rule_id in sorted(by_rule):
            lines.append(f"[{rule_id}] ({by_rule[rule_id][0].severity.value})")
            for v in by_rule[rule_id]:
                loc = ""
                if v.location is not None:
                    loc = f" — {v.location.file}:{v.location.start_line}"
                msg_lines = (v.message or "").splitlines() or [""]
                lines.append(f"  - [{v.key()}] {v.qualified_name}{loc}: {msg_lines[0]}")
                for cont in msg_lines[1:]:
                    lines.append(f"      {cont}" if cont else "")
            lines.append("")
        if self.suppressed:
            lines.append(f"({len(self.suppressed)} violation(s) silenced by baseline / ignore.)")
        for rule_id, reason in self.skipped:
            lines.append(f"[skipped] {rule_id}: {reason}")
        total_errors = sum(1 for v in self.violations if v.severity == Severity.ERROR)
        total_warnings = sum(1 for v in self.violations if v.severity == Severity.WARNING)
        lines.append(
            f"Summary: {total_errors} error(s), {total_warnings} warning(s)."
        )
        if self.violations:
            # Commented, because this text ends up inside `--log-out` files that
            # are handed straight back to `cdec baseline patch` — an uncommented
            # `[ALLOW]` in the guidance would read as a decision.
            lines.append(
                "# To accept any of these as known-and-allowed, quote its key:\n"
                "#   cdec baseline allow V-XXXXXXXX --reason \"why\"\n"
                "# Or mark them in bulk: add [ALLOW] to a line of this report and\n"
                "# apply it with `cdec baseline patch --file <report>`."
            )
        return "\n".join(lines) + "\n"

    def to_json(self) -> dict[str, Any]:
        return {
            "violations": [_v_to_json(v) for v in self.violations],
            "suppressed": [_v_to_json(v) for v in self.suppressed],
            "skipped": [{"rule_id": r, "reason": reason} for r, reason in self.skipped],
            "summary": {
                "errors": sum(1 for v in self.violations if v.severity == Severity.ERROR),
                "warnings": sum(1 for v in self.violations if v.severity == Severity.WARNING),
                "suppressed": len(self.suppressed),
            },
        }

    def write_json(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            json.dump(self.to_json(), fh, indent=2, sort_keys=True)


def _v_to_json(v: Violation) -> dict[str, Any]:
    out: dict[str, Any] = {
        "key": v.key(),
        "rule_id": v.rule_id,
        "severity": v.severity.value,
        "qualified_name": v.qualified_name,
        "message": v.message,
    }
    if v.signature:
        out["signature"] = v.signature
    if v.location is not None:
        out["location"] = {
            "file": v.location.file,
            "start_line": v.location.start_line,
            "end_line": v.location.end_line,
        }
    return out
