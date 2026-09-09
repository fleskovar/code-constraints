"""Rule: architectural-rule tags present in the baseline must not be removed
or modified in the current model.

This is the *drift* half of architectural-rule enforcement (Engine A). It never
inspects method bodies — it only compares the tag sets recorded on the baseline
(OLD) elements against the current (NEW) ones. The semantic question "does the
code actually obey the tag" is the job of the decoupled `cdec enforce` command.

A frozen tag is satisfied only when an identical tag (same name, same args, same
kwargs) still exists on the same element. Removing a tag or weakening its
parameters therefore fires — exactly the drift the user wants CI to block.
"""

from __future__ import annotations

from typing import Iterable

from code_constraints.core.model import Class, Operation
from code_constraints.lint.rules import register
from code_constraints.lint.rules.base import Rule, RuleContext, Violation, match_any_glob


@register("frozen-rules")
class FrozenRules(Rule):
    """Options:
      classes:  list[str] of qualified-name globs identifying locked classes
                (default: all classes)

    Scope must be `diff` — it needs a baseline to compare against.
    """

    def check(self, ctx: RuleContext) -> Iterable[Violation]:
        if not ctx.has_diff:
            return
        class_patterns: list[str] = list(self.options.get("classes") or ["*"])

        for qn, base_cls in ctx.baseline_class_by_qn.items():
            if self.is_ignored(qn):
                continue
            if not match_any_glob(qn, class_patterns):
                continue
            cur_cls = ctx.class_by_qn.get(qn)
            if cur_cls is None:
                # Whole class removed — that's `no-removed-classes`' job.
                continue

            yield from self._check_element(
                qn, signature=None, base=base_cls, cur=cur_cls, location=cur_cls.location
            )

            cur_ops = {o.signature(): o for o in cur_cls.operations}
            for base_op in base_cls.operations:
                if not base_op.rules:
                    continue
                cur_op = cur_ops.get(base_op.signature())
                if cur_op is None:
                    # Operation removed — `frozen-members` handles that.
                    continue
                yield from self._check_element(
                    qn,
                    signature=f"operation:{base_op.signature()}",
                    base=base_op,
                    cur=cur_op,
                    location=cur_cls.location,
                )

    def _check_element(
        self,
        qn: str,
        *,
        signature: str | None,
        base: Class | Operation,
        cur: Class | Operation,
        location,
    ) -> Iterable[Violation]:
        cur_rules = list(cur.rules)
        cur_by_name = {r.name: r for r in cur_rules}
        where = signature.split(":", 1)[1] if signature else qn
        for base_rule in base.rules:
            if base_rule in cur_rules:
                continue  # identical tag still present
            if base_rule.name in cur_by_name:
                action = "weakened"
                detail = (
                    f"architectural tag @{base_rule.name} on '{where}' was weakened "
                    f"(params changed from the baseline)."
                )
            else:
                action = "removed"
                detail = f"architectural tag @{base_rule.name} on '{where}' was removed."
            sig = f"{signature or 'class'}|@{base_rule.name}"
            yield self.emit(
                qualified_name=qn,
                signature=sig,
                message=self.message_for(
                    qualified_name=qn,
                    rule=base_rule.name,
                    member=where,
                    action=action,
                )
                or detail,
                location=location,
            )
