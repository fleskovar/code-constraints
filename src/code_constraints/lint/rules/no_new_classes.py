"""Rule: forbid adding new classes."""

from __future__ import annotations

from typing import Iterable

from code_constraints.core.model import DiffStatus
from code_constraints.lint.rules import register
from code_constraints.lint.rules.base import Rule, RuleContext, Violation, changed_classes


@register("no-new-classes")
class NoNewClasses(Rule):
    def check(self, ctx: RuleContext) -> Iterable[Violation]:
        if not ctx.has_diff:
            return
        for cls in changed_classes(ctx, only_status=DiffStatus.ADDED):
            if self.is_ignored(cls.qualified_name):
                continue
            yield self.emit(
                qualified_name=cls.qualified_name,
                message=self.message_for(qualified_name=cls.qualified_name)
                or f"New class '{cls.qualified_name}' was added.",
                location=cls.location,
            )
