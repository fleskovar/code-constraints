"""One engine-neutral view of a reported issue.

The three engines have three deliberately separate result types (`Violation`,
`Finding`, `LockViolation`). The review workflow needs to talk about all of them
in one file and one command, so this is the narrow projection they share — just
enough to print a line, identify it by key, and turn it into a waiver.

Adapting happens at the boundary (`collect.py`); the engines never learn about
this type, so they stay decoupled.
"""

from __future__ import annotations

from dataclasses import dataclass

from code_constraints.core.keys import make_key
from code_constraints.waivers.store import WAIVABLE_ENGINES, Waiver, now_stamp


class NotWaivable(ValueError):
    """Raised when something tries to waive an issue that must not be waived."""


@dataclass
class Issue:
    """A single reported issue, from any engine."""

    engine: str  # "check" | "enforce" | "lock"
    rule: str  # rule id / catalog rule / lock violation kind
    qualified_name: str  # class qname, or lock target
    detail: str = ""  # discriminator; see code_constraints.core.keys
    message: str = ""
    severity: str = "error"
    file: str = ""
    line: int = 0
    # True when a waiver already covers this issue (it was silenced this run).
    waived: bool = False
    waiver_reason: str = ""

    @property
    def key(self) -> str:
        return make_key(self.engine, self.rule, self.qualified_name, self.detail)

    @property
    def waivable(self) -> bool:
        return self.engine in WAIVABLE_ENGINES

    @property
    def location(self) -> str:
        if not self.file:
            return ""
        return f"{self.file}:{self.line}" if self.line else self.file

    def to_waiver(self, reason: str = "", actor: str = "") -> Waiver:
        if not self.waivable:
            raise NotWaivable(_not_waivable_message(self))
        return Waiver(
            engine=self.engine,
            rule=self.rule,
            qualified_name=self.qualified_name,
            detail=self.detail,
            reason=reason,
            added=now_stamp(),
            added_by=actor,
        )


def _not_waivable_message(issue: Issue) -> str:
    """Locks are the only non-waivable engine, and the message has to say what
    to do instead — a dead end here is a dead end for the whole workflow."""
    if issue.engine == "lock":
        return (
            f"{issue.key} is a lock violation on '{issue.qualified_name}', and locks "
            f"are not waivable through the baseline. A frozen implementation may "
            f"only change with a lead's approval, which leaves a reviewable diff on "
            f".cdec/locks.yaml:\n"
            f"    cdec lock set --target {issue.qualified_name} --force --reason \"why\"\n"
            f"To drop the lock entirely:\n"
            f"    cdec lock remove --target {issue.qualified_name}"
        )
    return f"{issue.key}: issues from engine {issue.engine!r} cannot be waived."
