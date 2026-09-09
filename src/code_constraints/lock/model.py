"""Result types for the `cdec lock` implementation-freeze engine (Engine C).

Deliberately separate from `code_constraints.lint.Violation` and
`code_constraints.enforce.Finding`: the
three engines are decoupled by design and share only the rule *catalog*.

  * `cdec check`   (Engine A) — did the architectural *intent* drift?
  * `cdec enforce` (Engine B) — does the code *obey* the tags right now?
  * `cdec lock`    (Engine C) — did a frozen implementation *change at all*?

Engine C is the only one that cares about the exact contents of a body. It
compares an AST-derived digest against the digest recorded in `.cdec/locks.yaml`,
so reformatting, comment edits, and moving the element around a file never trip
a lock, while any semantic edit does.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from typing import Any, Iterable, Literal

from code_constraints.core.keys import make_key

# Catalog id of the tag that declares a lock. Never hard-code this elsewhere —
# import it (or look it up via `code_constraints.core.rules.by_id`).
LOCK_RULE = "locked"

TargetKind = Literal["class", "method", "function"]
ViolationKind = Literal["changed", "missing", "removed", "unlocked", "algo-mismatch"]


@dataclass
class LockTarget:
    """A lockable element discovered in the current source tree.

    Produced by the per-language fingerprinters (`code_constraints/{python,csharp}
    .fingerprint`). `digest` is over the *normalised* AST: position-independent,
    comment-free, and (by default) docstring-free.

    Overloads / same-named siblings in one scope collapse into a single target
    whose digest covers the whole group, so adding an overload to a locked
    method is itself a lock violation and no ordinal disambiguator is needed.
    """

    target: str  # dotted identity, e.g. "orders.Receipt.formatted"
    kind: TargetKind
    digest: str  # hex sha256 of the canonical AST serialisation
    algo: str  # digest algorithm id, e.g. "py-ast/1"
    file: str = ""
    line: int = 0
    declared: bool = False  # carries an explicit @locked / [Locked] tag
    params: dict[str, str] = field(default_factory=dict)  # tag kwargs (reason/owner)

    @property
    def reason(self) -> str:
        return self._param("reason")

    @property
    def owner(self) -> str:
        return self._param("owner")

    def _param(self, name: str) -> str:
        """Tag params are case-insensitive: Python writes `reason=`, C# writes
        `Reason =`, and both land in the same catalog param."""
        for key, value in self.params.items():
            if key.lower() == name:
                return _unquote(value)
        return ""


@dataclass
class LockEntry:
    """One recorded lock in `.cdec/locks.yaml` — the approved digest."""

    target: str
    kind: str
    digest: str
    algo: str
    file: str = ""
    locked_at: str = ""
    locked_by: str = ""
    reason: str = ""
    # True when the lock came from a `lock.targets:` glob rather than a tag.
    # Glob-locked entries are exempt from the "tag was removed" check.
    via_pattern: bool = False


@dataclass
class LockViolation:
    kind: ViolationKind
    target: str
    message: str
    file: str = ""
    line: int = 0
    expected: str = ""
    actual: str = ""
    reason: str = ""
    owner: str = ""

    def fingerprint(self) -> tuple[str, str]:
        return (self.kind, self.target)

    def key(self) -> str:
        """Stable review key (`L-…`) — see `code_constraints.core.keys`.

        Locks are the one thing `cdec baseline` will not waive: accepting a
        changed implementation is `cdec lock set --force`, a privileged,
        reviewable act. The key exists anyway so reports are uniform and an
        agent can name the lock it means.
        """
        return make_key("lock", self.kind, self.target, "")


@dataclass
class LockReport:
    violations: list[LockViolation] = field(default_factory=list)
    checked: int = 0  # number of lockfile entries verified
    declared: int = 0  # number of @locked elements found in source
    bypassed: bool = False
    bypass_reason: str = ""

    @property
    def ok(self) -> bool:
        """True when nothing blocks the build. A bypassed run is never a
        failure — but `bypassed` stays in the report so CI can reject it."""
        return self.bypassed or not self.violations


# ---------- rendering ----------

_KIND_HEADLINE: dict[str, str] = {
    "changed": "frozen implementation changed",
    "missing": "declared @locked but not baselined",
    "removed": "frozen element no longer exists",
    "unlocked": "@locked tag was removed",
    "algo-mismatch": "digest algorithm changed",
}


def format_report(report: LockReport) -> str:
    if report.bypassed:
        head = [
            "!" * 72,
            "cdec lock: LOCKS BYPASSED — frozen implementations were NOT verified.",
        ]
        if report.bypass_reason:
            head.append(f"          reason: {report.bypass_reason}")
        head.append(
            f"          {len(report.violations)} lock violation(s) suppressed."
        )
        head.append("!" * 72)
        return "\n".join(head) + "\n"
    if not report.violations:
        return (
            f"cdec lock: {report.checked} locked element(s) verified, no changes.\n"
        )

    by_kind: dict[str, list[LockViolation]] = {}
    for v in report.violations:
        by_kind.setdefault(v.kind, []).append(v)

    lines = [f"cdec lock: {len(report.violations)} lock violation(s):"]
    for kind in sorted(by_kind):
        lines.append(f"[{kind}] {_KIND_HEADLINE.get(kind, '')}")
        for v in sorted(by_kind[kind], key=lambda x: x.target):
            loc = f" — {v.file}:{v.line}" if v.file else ""
            lines.append(f"  - [{v.key()}] {v.target}{loc}")
            for cont in (v.message or "").splitlines():
                lines.append(f"      {cont}" if cont else "")
        lines.append("")
    lines.append(
        "A locked implementation may only change with a lead's approval:\n"
        "  cdec lock set --target <name> --force --reason \"<why>\"\n"
        "To ship without re-baselining (audited, discouraged):\n"
        "  cdec check --bypass-locks --bypass-reason \"<why>\""
    )
    return "\n".join(lines) + "\n"


def report_to_json(report: LockReport) -> dict[str, Any]:
    return {
        "violations": [
            {
                "key": v.key(),
                "kind": v.kind,
                "target": v.target,
                "message": v.message,
                "file": v.file,
                "line": v.line,
                "expected": v.expected,
                "actual": v.actual,
                "reason": v.reason,
                "owner": v.owner,
            }
            for v in report.violations
        ],
        "summary": {
            "checked": report.checked,
            "declared": report.declared,
            "violations": len(report.violations),
            "bypassed": report.bypassed,
            "bypass_reason": report.bypass_reason,
        },
    }


# ---------- helpers ----------

def match_any_glob(name: str, patterns: Iterable[str]) -> bool:
    """Glob match with `.` treated as a normal character, so `tests.**` matches
    every descendant of `tests`. Mirrors `code_constraints.lint.rules.base.match_any_glob`;
    duplicated rather than imported to keep the engines decoupled."""
    for p in patterns:
        if fnmatch.fnmatchcase(name, p.replace("**", "*")):
            return True
    return False


def _unquote(raw: str) -> str:
    """Tag kwargs hold raw source text, so a Python `reason="x"` arrives as
    `'"x"'` and a C# one as `"\"x\""`. Strip one layer of matching quotes."""
    text = raw.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    return text
