"""Rule: forbid changes (add/remove/change) to attributes or operations on
a selected set of classes."""

from __future__ import annotations

from typing import Iterable

from code_constraints.core.model import DiffStatus
from code_constraints.lint.rules import register
from code_constraints.lint.rules.base import Rule, RuleContext, Violation, match_any_glob


@register("frozen-members")
class FrozenMembers(Rule):
    """Options:
      classes:  list[str] of qualified-name globs identifying the locked classes
      members:  optional list[str] of member-name or signature globs (default: all)
      kinds:    optional list, subset of ["attribute", "operation"] (default: both)
    """

    def check(self, ctx: RuleContext) -> Iterable[Violation]:
        if not ctx.has_diff:
            return
        class_patterns: list[str] = list(self.options.get("classes") or ["*"])
        member_patterns: list[str] = list(self.options.get("members") or ["*"])
        kinds: list[str] = list(self.options.get("kinds") or ["attribute", "operation"])

        for cls in ctx.project.iter_classes():
            if self.is_ignored(cls.qualified_name):
                continue
            if not match_any_glob(cls.qualified_name, class_patterns):
                continue
            members: list[tuple[str, object]] = []
            if "attribute" in kinds:
                members.extend(("attribute", a) for a in cls.attributes)
            if "operation" in kinds:
                members.extend(("operation", o) for o in cls.operations)
            for kind, member in members:
                status = getattr(member, "status", DiffStatus.UNCHANGED)
                if status == DiffStatus.UNCHANGED:
                    continue
                name = getattr(member, "name", "")
                sig = member.signature() if hasattr(member, "signature") else name
                if not (
                    match_any_glob(name, member_patterns)
                    or match_any_glob(sig, member_patterns)
                ):
                    continue
                action = {
                    DiffStatus.ADDED: "added",
                    DiffStatus.REMOVED: "removed",
                    DiffStatus.CHANGED: "changed",
                }.get(status, str(status))
                yield self.emit(
                    qualified_name=cls.qualified_name,
                    signature=f"{kind}:{sig}",
                    message=self.message_for(
                        qualified_name=cls.qualified_name,
                        member=sig,
                        kind=kind,
                        action=action,
                    )
                    or f"{kind.capitalize()} '{sig}' on '{cls.qualified_name}' was {action}.",
                    location=cls.location,
                )
