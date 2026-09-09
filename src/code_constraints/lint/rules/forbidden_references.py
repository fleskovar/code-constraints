"""Rule: forbid classes in `from` from referencing classes in `to`."""

from __future__ import annotations

from typing import Iterable

from code_constraints.core.model import DiffStatus
from code_constraints.lint.rules import register
from code_constraints.lint.rules.base import Rule, RuleContext, Violation, match_any_glob


@register("forbidden-references")
class ForbiddenReferences(Rule):
    """Options:
      from:  list[str] of qualified-name globs (source side)
      to:    list[str] of qualified-name globs (target side)
    """

    def check(self, ctx: RuleContext) -> Iterable[Violation]:
        from_patterns: list[str] = list(self.options.get("from") or [])
        to_patterns: list[str] = list(self.options.get("to") or [])
        if not from_patterns or not to_patterns:
            return
        for cls in ctx.project.iter_classes():
            if cls.status == DiffStatus.REMOVED:
                continue
            src_qn = cls.qualified_name
            if self.is_ignored(src_qn):
                continue
            if not match_any_glob(src_qn, from_patterns):
                continue
            if self.scope == "diff" and ctx.has_diff:
                if cls.status not in (DiffStatus.ADDED, DiffStatus.CHANGED):
                    continue
            for tgt_qn in ctx.outgoing_refs.get(src_qn, set()):
                if self.is_ignored(tgt_qn):
                    continue
                if not match_any_glob(tgt_qn, to_patterns):
                    continue
                yield self.emit(
                    qualified_name=src_qn,
                    signature=f"->{tgt_qn}",
                    message=self.message_for(
                        qualified_name=src_qn, source=src_qn, target=tgt_qn
                    )
                    or f"'{src_qn}' is not allowed to reference '{tgt_qn}'.",
                    location=cls.location,
                )
