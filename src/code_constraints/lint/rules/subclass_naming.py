"""Rule: enforce a naming pattern on classes inheriting from a base/interface.

Example: every implementation of `IFactory` must end in `Factory`.
"""

from __future__ import annotations

import re
from typing import Iterable

from code_constraints.core.model import DiffStatus
from code_constraints.lint.rules import register
from code_constraints.lint.rules.base import Rule, RuleContext, Violation, match_any_glob


@register("subclass-naming")
class SubclassNaming(Rule):
    """Options:
      base:          glob pattern matched against entries in `Class.bases`
                     (e.g. "IFactory", "*.IFactory")
      name_pattern:  regex applied to the class name (full match)
    """

    def check(self, ctx: RuleContext) -> Iterable[Violation]:
        base_pattern = self.options.get("base")
        name_pattern = self.options.get("name_pattern")
        if not base_pattern or not name_pattern:
            return
        try:
            regex = re.compile(name_pattern)
        except re.error as exc:  # pragma: no cover - config-validation territory
            raise ValueError(
                f"subclass-naming: invalid name_pattern regex {name_pattern!r}: {exc}"
            ) from exc

        base_globs = base_pattern if isinstance(base_pattern, list) else [base_pattern]

        for cls in ctx.project.iter_classes():
            if cls.status == DiffStatus.REMOVED:
                continue
            if self.is_ignored(cls.qualified_name):
                continue
            if self.scope == "diff" and ctx.has_diff:
                if cls.status not in (DiffStatus.ADDED, DiffStatus.CHANGED):
                    continue
            # Match if any of the class's bases matches the configured base.
            # We match both the literal base text and its short name (last
            # dotted segment) so callers can write either "IFactory" or
            # "myapp.factories.IFactory".
            matched = False
            for base in cls.bases:
                short = base.split(".")[-1]
                if match_any_glob(base, base_globs) or match_any_glob(short, base_globs):
                    matched = True
                    break
            if not matched:
                continue
            if regex.fullmatch(cls.name):
                continue
            yield self.emit(
                qualified_name=cls.qualified_name,
                message=self.message_for(
                    qualified_name=cls.qualified_name,
                    name=cls.name,
                    base=base_pattern,
                    pattern=name_pattern,
                )
                or f"Class '{cls.qualified_name}' inherits from {base_pattern!r} "
                f"but its name does not match /{name_pattern}/.",
                location=cls.location,
            )
