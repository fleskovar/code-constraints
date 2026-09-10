"""Rule base class, Violation dataclass, RuleContext."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterable

from code_constraints.core.keys import make_key
from code_constraints.core.model import Class, DiffStatus, Project, SourceLocation


class RuleSkipped(RuntimeError):
    """Raised by a rule that cannot run at all in this project.

    Recorded in `Report.skipped` rather than swallowed: a rule that quietly
    checks nothing looks exactly like a rule that passed, and that is how a
    guardrail stops guarding without anybody noticing.
    """


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
    # `signature` is used by the exception fingerprint so that frozen-members
    # violations on the same class can be distinguished by member.
    signature: str | None = None
    # --- key identity -------------------------------------------------------
    # A key names the *issue*, not the config entry that surfaced it. Rules that
    # adapt one of the decoupled engines (tag conformance, locks, the reference
    # gate) therefore key their violations under that engine's own identity, so
    # renaming a `rules.yaml` entry never invalidates a granted exception and a
    # key recorded before the CLI was unified still resolves. Native rules leave
    # these unset and key as `check`/`rule_id`, exactly as they always have.
    key_engine: str = "check"
    key_rule: str | None = None
    # False for issues that must not be accepted as exceptions — locks, whose
    # escape hatch is a privileged re-baseline instead.
    waivable: bool = True

    def fingerprint(self) -> tuple[str, str, str]:
        return (self.rule_id, self.qualified_name, self.signature or "")

    def key(self) -> str:
        """Stable review key. Derived from the issue identity, so it never moves
        when the file does — see `code_constraints.core.keys`."""
        return make_key(
            self.key_engine,
            self.key_rule or self.rule_id,
            self.qualified_name,
            self.signature or "",
        )


@dataclass
class RuleContext:
    """Per-run context, built once and passed to every rule.

    The annotated project carries DiffStatus values when a baseline was used;
    `has_diff` is False when running in snapshot-only mode (no baseline).
    """
    project: Project
    has_diff: bool
    # --- source-level context ----------------------------------------------
    # Most rules read only the model. The rules that adapt an engine which
    # re-parses bodies (tag conformance, locks) or loads another model (the
    # reference gate) need to know where the code and the config live. The
    # engines themselves stay independent packages: these rules are adapters
    # that import them lazily and translate their results into `Violation`s.
    source: Path | None = None
    language: str = ""
    config_dir: Path | None = None
    reference_path: Path | None = None
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
    #: Scope used when the entry doesn't say. Rules that compare against a
    #: baseline override this to "diff".
    default_scope: str = "snapshot"
    #: True when the rule can record the current state as the new approved
    #: baseline via `accept_current_state` (locks, the reference gate).
    supports_auto_accept: bool = False

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

    # ---- override hooks ----
    def check(self, ctx: RuleContext) -> Iterable[Violation]:
        raise NotImplementedError

    def accept_current_state(self, ctx: RuleContext, *, force: bool = False) -> list[str]:
        """Record the code as it stands now as this rule's approved baseline.

        Called by `cdec check --automatic-exceptions`. Rules whose issues are
        grandfathered through the `exceptions:` list don't implement this — it
        exists for the two rules that carry a baseline of their own: the lock
        ledger and the reference snapshot. Returns lines describing what
        changed, for the command to print.
        """
        return []


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
