"""One engine-neutral view of a reported issue.

The engines have deliberately separate result types (`Violation`, `Finding`,
`LockViolation`, `Deviation`). The review workflow needs to talk about all of
them in one list, so this is the narrow projection they share — just enough to
print a line, identify it by key, and turn it into an exception.

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

    engine: str  # "check" | "enforce" | "lock" | "reference"
    rule: str  # the engine's own rule identity — what the key is derived from
    qualified_name: str  # class qname, or lock target
    detail: str = ""  # discriminator; see code_constraints.core.keys
    message: str = ""
    severity: str = "error"
    file: str = ""
    line: int = 0
    # The `rules.yaml` entry that surfaced this issue. Shown to the reader so a
    # report points at the line of config to edit; never part of the key, so
    # renaming an entry doesn't invalidate an exception granted against it.
    rule_id: str = ""
    # False for issues that must not be accepted as exceptions — locks.
    waivable: bool = True
    # True when an exception already covers this issue (it was silenced).
    waived: bool = False
    waiver_reason: str = ""

    def __post_init__(self) -> None:
        if not self.rule_id:
            self.rule_id = self.rule
        # The engine is the authority on waivability; a caller can only narrow.
        if self.engine not in WAIVABLE_ENGINES:
            self.waivable = False

    @property
    def key(self) -> str:
        return make_key(self.engine, self.rule, self.qualified_name, self.detail)

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
    """Locks are the only non-exceptable engine, and the message has to say what
    to do instead — a dead end here is a dead end for the whole workflow."""
    if issue.engine == "lock":
        return (
            f"{issue.key} is a lock violation on '{issue.qualified_name}', and locks "
            f"cannot be accepted as exceptions. A frozen implementation may only "
            f"change with a lead's approval, which leaves a reviewable diff on the "
            f"`locks:` section of .cdec/rules.yaml:\n"
            f"    cdec check --automatic-exceptions locks --force\n"
            f"To drop the lock entirely, delete its @locked tag from the source and "
            f"re-run that command."
        )
    return f"{issue.key}: issues from engine {issue.engine!r} cannot be accepted."
