"""Rule: the code must not deviate structurally from the reference model.

The adapter for the reference gate (`code_constraints.reference`). Where the
other rules are scalpels — each one enforcing exactly the law you wrote down —
this one is a wall: *any* structural difference from the committed
`.cdec/reference.xmi` fails.

It earns its place beside `frozen-members` because the two sit on different
comparison engines. The diff engine matches members by signature and only calls
a matched member changed when its *rule tags* differ, so it is blind to
visibility changes (`public` -> `private`), modifier changes (`static`,
`abstract`, `readonly`) and class-kind changes. The reference comparator walks
both models field by field and catches all of them. A pull request that flips a
public method to private passes `frozen-members` and fails this.

Generating the reference is `cdec check --automatic-exceptions reference`, which
is what `accept_current_state` below does: re-snapshot the source and commit the
new model in the same pull request, so the architectural delta is reviewable.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from code_constraints.lint.rules import register
from code_constraints.lint.rules.base import Rule, RuleContext, RuleSkipped, Violation


@register("reference-architecture")
class ReferenceArchitecture(Rule):
    """Options:
      reference:  path to the reference model, relative to the project root
                  (default: the project's `reference:` setting, else
                  `.cdec/reference.xmi`).
      categories: optional list[str] of deviation categories to enforce, e.g.
                  ["class-removed", "operation-changed"]. Default: all of them.
    """

    supports_auto_accept = True

    def reference_path(self, ctx: RuleContext) -> Path:
        configured = self.options.get("reference")
        if configured:
            base = ctx.config_dir.parent if ctx.config_dir else Path(".")
            path = Path(str(configured))
            return path if path.is_absolute() else (base / path)
        if ctx.reference_path is not None:
            return ctx.reference_path
        raise RuleSkipped("no reference model configured")

    def check(self, ctx: RuleContext) -> Iterable[Violation]:
        path = self.reference_path(ctx)
        if not path.is_file():
            raise RuleSkipped(
                f"reference model not found: {path}. Snapshot one with "
                f"`cdec check --automatic-exceptions reference`."
            )
        from code_constraints.core.model_io import load_model
        from code_constraints.reference import compare_to_reference

        if ctx.source is None or not ctx.language:
            raise RuleSkipped("no source tree resolved")

        # The rule compares against the *current* parse, never the annotated
        # diff project: a removed class is still present (marked REMOVED) in the
        # annotated model, and the gate must see it as gone.
        from code_constraints.lint.pipeline import parse_source

        try:
            deviations = compare_to_reference(
                load_model(path), parse_source(ctx.source, ctx.language)
            )
        except ValueError as exc:
            raise RuleSkipped(str(exc)) from exc

        only = {str(c) for c in (self.options.get("categories") or [])}
        for deviation in deviations:
            if only and deviation.category not in only:
                continue
            if self.is_ignored(deviation.qualified_name):
                continue
            yield Violation(
                rule_id=self.rule_id,
                severity=self.severity,
                qualified_name=deviation.qualified_name,
                message=self.message_for(
                    qualified_name=deviation.qualified_name,
                    category=deviation.category,
                    member=deviation.member or "",
                    message=deviation.message,
                )
                or deviation.message,
                signature=deviation.member or deviation.category,
                key_engine="reference",
                key_rule=deviation.category,
            )

    def accept_current_state(self, ctx: RuleContext, *, force: bool = False) -> list[str]:
        """Re-snapshot the reference from the current source."""
        if ctx.source is None or not ctx.language:
            raise RuleSkipped("no source tree resolved")
        from code_constraints.core.model_io import save_model
        from code_constraints.lint.pipeline import parse_source

        path = self.reference_path(ctx)
        project = parse_source(ctx.source, ctx.language)
        path.parent.mkdir(parents=True, exist_ok=True)
        save_model(project, path)
        n_classes = sum(1 for _ in project.iter_classes())
        return [f"  wrote {path} ({n_classes} class(es) snapshotted from {ctx.source})"]
