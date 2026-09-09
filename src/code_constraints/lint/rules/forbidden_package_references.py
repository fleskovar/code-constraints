"""Rule: forbid packages in `from` from referencing packages in `to`.

Edges between packages are derived from class-level outgoing references
(aggregated by containing package), matching the logic in
`code_constraints.core.graph_model.build_package_graph`.
"""

from __future__ import annotations

from typing import Iterable

from code_constraints.lint.rules import register
from code_constraints.lint.rules.base import Rule, RuleContext, Violation, match_any_glob


@register("forbidden-package-references")
class ForbiddenPackageReferences(Rule):
    """Options:
      from:  list[str] of package qualified-name globs
      to:    list[str] of package qualified-name globs
    """

    def check(self, ctx: RuleContext) -> Iterable[Violation]:
        from_patterns: list[str] = list(self.options.get("from") or [])
        to_patterns: list[str] = list(self.options.get("to") or [])
        if not from_patterns or not to_patterns:
            return
        for src_pkg, tgt_pkgs in ctx.outgoing_pkg_refs.items():
            if self.is_ignored(src_pkg):
                continue
            if not match_any_glob(src_pkg, from_patterns):
                continue
            for tgt_pkg in tgt_pkgs:
                if tgt_pkg == src_pkg:
                    continue
                if self.is_ignored(tgt_pkg):
                    continue
                if not match_any_glob(tgt_pkg, to_patterns):
                    continue
                yield self.emit(
                    qualified_name=src_pkg,
                    signature=f"->{tgt_pkg}",
                    message=self.message_for(
                        qualified_name=src_pkg, source=src_pkg, target=tgt_pkg
                    )
                    or f"Package '{src_pkg}' is not allowed to reference package '{tgt_pkg}'.",
                )
