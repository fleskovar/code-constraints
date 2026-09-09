"""Rule base class, Violation dataclass, RuleContext."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable

from code_constraints.core.keys import make_key
from code_constraints.core.model import Class, DiffStatus, Project, SourceLocation


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    OFF = "off"


@dataclass
class Violation:
    rule_id: str
    severity: Severity
    qualified_name: str
    message: str
    location: SourceLocation | None = None
    # `signature` is used by the baseline fingerprint so that frozen-members
    # violations on the same class can be distinguished by member.
    signature: str | None = None

    def fingerprint(self) -> tuple[str, str, str]:
        return (self.rule_id, self.qualified_name, self.signature or "")

    def key(self) -> str:
        """Stable review key (`V-…`). Derived from the fingerprint, so it never
        moves when the file does — see `code_constraints.core.keys`."""
        return make_key("check", self.rule_id, self.qualified_name, self.signature or "")


@dataclass
class RuleContext:
    """Per-run context, built once and passed to every rule.

    The annotated project carries DiffStatus values when a baseline was used;
    `has_diff` is False when running in snapshot-only mode (no baseline).
    """
    project: Project
    has_diff: bool
    # Cached: qualified_name -> set of qualified names that reference it
    # (attribute type or base class).
    incoming_refs: dict[str, set[str]] = field(default_factory=dict)
    # qualified_name -> set of qualified names this class references.
    outgoing_refs: dict[str, set[str]] = field(default_factory=dict)
    # package qualified_name -> set of package qualified names it references.
    outgoing_pkg_refs: dict[str, set[str]] = field(default_factory=dict)
    # class qualified_name -> Class
    class_by_qn: dict[str, Class] = field(default_factory=dict)
    # class qualified_name -> containing package qualified_name
    class_to_package: dict[str, str] = field(default_factory=dict)
    # Baseline (OLD side) classes by qualified name; populated only when a
    # baseline project was supplied. Used by diff-scope rules that need the
    # *previous* element state (e.g. frozen-rules), since the annotated
    # `project` carries the NEW rule lists, not the old ones.
    baseline_class_by_qn: dict[str, Class] = field(default_factory=dict)


def match_any_glob(name: str, patterns: Iterable[str]) -> bool:
    """Match `name` against any of the patterns. Patterns use shell glob
    semantics with `.` treated as a normal character (so `foo.bar.*` matches
    `foo.bar.baz` and `foo.**` matches every descendant)."""
    for p in patterns:
        # Treat `**` as matching across dot-separated segments. `fnmatch` already
        # treats `*` as any char including `.`, so `foo.**` collapses to
        # `foo.*` for matching purposes — which is what we want.
        pat = p.replace("**", "*")
        if fnmatch.fnmatchcase(name, pat):
            return True
    return False


class Rule:
    """Subclasses are instantiated once per `rules.yaml` entry."""

    type_name: str = ""  # set by @register

    def __init__(
        self,
        rule_id: str,
        severity: Severity,
        scope: str,
        message: str,
        ignore: list[str],
        options: dict[str, Any],
    ) -> None:
        self.rule_id = rule_id
        self.severity = severity
        self.scope = scope  # "diff" | "snapshot"
        self.message_template = message
        self.ignore = list(ignore or [])
        self.options = options

    # ---- helpers shared by subclasses ----
    def is_ignored(self, qualified_name: str) -> bool:
        return match_any_glob(qualified_name, self.ignore)

    def message_for(self, **fmt: Any) -> str:
        if not self.message_template:
            return ""
        try:
            return self.message_template.format(**fmt)
        except (KeyError, IndexError):
            return self.message_template

    def emit(
        self,
        qualified_name: str,
        message: str,
        location: SourceLocation | None = None,
        signature: str | None = None,
    ) -> Violation:
        return Violation(
            rule_id=self.rule_id,
            severity=self.severity,
            qualified_name=qualified_name,
            message=message or self.message_template,
            location=location,
            signature=signature,
        )

    # ---- override hook ----
    def check(self, ctx: RuleContext) -> Iterable[Violation]:
        raise NotImplementedError


def changed_classes(ctx: RuleContext, only_status: DiffStatus | None = None) -> Iterable[Class]:
    """Yield classes whose status matches `only_status`; or all non-unchanged
    classes when `only_status` is None. Skips the iteration entirely when
    the context isn't from a diff."""
    if not ctx.has_diff:
        return
    for cls in ctx.project.iter_classes():
        if only_status is None:
            if cls.status != DiffStatus.UNCHANGED:
                yield cls
        elif cls.status == only_status:
            yield cls
