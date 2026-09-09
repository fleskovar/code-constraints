"""Rule: cap the number of distinct outgoing class references on any class."""

from __future__ import annotations

from typing import Iterable

from code_constraints.core.model import DiffStatus
from code_constraints.lint.rules import register
from code_constraints.lint.rules.base import Rule, RuleContext, Violation


@register("max-class-fanout")
class MaxClassFanout(Rule):
    """Options:
      limit:  int, maximum allowed distinct outgoing references (default 10)
    """

    def check(self, ctx: RuleContext) -> Iterable[Violation]:
        try:
            limit = int(self.options.get("limit", 10))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"max-class-fanout: 'limit' must be an integer: {exc}") from exc
        for cls in ctx.project.iter_classes():
            if cls.status == DiffStatus.REMOVED:
                continue
            if self.is_ignored(cls.qualified_name):
                continue
            if self.scope == "diff" and ctx.has_diff:
                if cls.status not in (DiffStatus.ADDED, DiffStatus.CHANGED):
                    continue
            fanout = len(ctx.outgoing_refs.get(cls.qualified_name, set()))
            if fanout <= limit:
                continue
            yield self.emit(
                qualified_name=cls.qualified_name,
                message=self.message_for(
                    qualified_name=cls.qualified_name, fanout=fanout, limit=limit
                )
                or f"Class '{cls.qualified_name}' has fanout {fanout} (limit: {limit}).",
                location=cls.location,
            )
