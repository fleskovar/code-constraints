"""Format the `cdec check` output as human-readable text or JSON."""

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
    # Rules that couldn't run (e.g. a diff-scope rule with no baseline, or a
    # language with no AST fingerprinter). Reported, never swallowed.
    skipped: list[tuple[str, str]] = field(default_factory=list)
    # Lock violations held back by `--bypass-locks`: reported under an audit
    # banner and flagged in JSON, but not counted as failures.
    bypassed: list[Violation] = field(default_factory=list)
    bypass_reason: str = ""

    def has_failures(self, fail_on: Severity) -> bool:
        if fail_on == Severity.OFF:
            return False
        if fail_on == Severity.WARNING:
            return any(v.severity in (Severity.ERROR, Severity.WARNING) for v in self.violations)
        # default: error
        return any(v.severity == Severity.ERROR for v in self.violations)

    def to_human(self) -> str:
        lines: list[str] = []
        if self.bypassed:
            lines.extend(self._bypass_banner())
        if not self.violations:
            lines.append("cdec check: no violations.")
        else:
            lines.extend(self._violation_lines())
        if self.suppressed:
            lines.append(
                f"({len(self.suppressed)} violation(s) silenced by an exception / ignore.)"
            )
        for rule_id, reason in self.skipped:
            lines.append(f"[skipped] {rule_id}: {reason}")
        total_errors = sum(1 for v in self.violations if v.severity == Severity.ERROR)
        total_warnings = sum(1 for v in self.violations if v.severity == Severity.WARNING)
        lines.append(f"Summary: {total_errors} error(s), {total_warnings} warning(s).")
        lines.extend(self._guidance())
        return "\n".join(lines) + "\n"

    def _violation_lines(self) -> list[str]:
        lines: list[str] = []
        by_rule: dict[str, list[Violation]] = {}
        for v in self.violations:
            by_rule.setdefault(v.rule_id, []).append(v)
        for rule_id in sorted(by_rule):
            group = by_rule[rule_id]
            lines.append(f"[{rule_id}] ({group[0].severity.value})")
            if not group[0].waivable:
                lines.append(
                    "  NOT EXCEPTABLE: a frozen implementation changes only via "
                    "`cdec check --automatic-exceptions locks --force`."
                )
            for v in group:
                loc = ""
                if v.location is not None:
                    loc = f" — {v.location.file}:{v.location.start_line}"
                msg_lines = (v.message or "").splitlines() or [""]
                lines.append(f"  - [{v.key()}] {v.qualified_name}{loc}: {msg_lines[0]}")
                for cont in msg_lines[1:]:
                    lines.append(f"      {cont}" if cont else "")
            lines.append("")
        return lines

    def _bypass_banner(self) -> list[str]:
        lines = [
            "!" * 72,
            "cdec check: LOCKS BYPASSED — frozen implementations were NOT enforced.",
        ]
        if self.bypass_reason:
            lines.append(f"          reason: {self.bypass_reason}")
        lines.append(f"          {len(self.bypassed)} lock violation(s) suppressed:")
        for v in sorted(self.bypassed, key=lambda x: x.qualified_name):
            lines.append(f"            - [{v.key()}] {v.qualified_name}")
        lines.append("!" * 72)
        lines.append("")
        return lines

    def _guidance(self) -> list[str]:
        """Commented on purpose: this text lands inside `--log-out` files that
        are handed straight back to `cdec exceptions patch`, and an uncommented
        `[ALLOW]` in the guidance would read as a decision."""
        example = next((v.key() for v in self.violations if v.waivable), "")
        if not example:
            return []
        # Quote a key that is actually in this report, so the line can be copied
        # rather than adapted.
        return [
            "# To accept any of these as known-and-allowed, quote its key:\n"
            f"#   cdec exceptions allow {example} --reason \"why\"\n"
            "# Or mark them in bulk: add [ALLOW] to a line of this report and\n"
            "# apply it with `cdec exceptions patch --file <report>`."
        ]

    def to_json(self) -> dict[str, Any]:
        return {
            "violations": [_v_to_json(v) for v in self.violations],
            "suppressed": [_v_to_json(v) for v in self.suppressed],
            "bypassed": [_v_to_json(v) for v in self.bypassed],
            "skipped": [{"rule_id": r, "reason": reason} for r, reason in self.skipped],
            "summary": {
                "errors": sum(1 for v in self.violations if v.severity == Severity.ERROR),
                "warnings": sum(1 for v in self.violations if v.severity == Severity.WARNING),
                "suppressed": len(self.suppressed),
                "skipped": len(self.skipped),
                # Kept as a top-level flag so a pipeline can reject a bypassed
                # run on a protected branch with one JSON lookup.
                "bypassed": bool(self.bypassed),
                "bypass_reason": self.bypass_reason,
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
        "engine": v.key_engine,
        "severity": v.severity.value,
        "qualified_name": v.qualified_name,
        "message": v.message,
        "waivable": v.waivable,
    }
    if v.key_rule:
        out["rule"] = v.key_rule
    if v.signature:
        out["signature"] = v.signature
    if v.location is not None:
        out["location"] = {
            "file": v.location.file,
            "start_line": v.location.start_line,
            "end_line": v.location.end_line,
        }
    return out
