"""Rule: flag classes that have no incoming references."""

from __future__ import annotations

from typing import Iterable

from code_constraints.core.model import Class, DiffStatus
from code_constraints.lint.rules import register
from code_constraints.lint.rules.base import Rule, RuleContext, Violation, match_any_glob

# Framework base classes whose subclasses are instantiated by the framework
# (Unity scenes, the editor, networking) rather than by project code, so they
# legitimately have no incoming reference. Treated as entry points.
_DEFAULT_FRAMEWORK_BASES = (
    "MonoBehaviour",
    "ScriptableObject",
    "NetworkBehaviour",
    "StateMachineBehaviour",
    "Editor",
    "EditorWindow",
    "PropertyDrawer",
    "ScriptableWizard",
)


@register("dangling-classes")
class DanglingClasses(Rule):
    """A class is "dangling" when no other project class references it
    (no attribute, method signature, method-body usage, or base resolves to it)
    and it isn't in the configured `entry_points` allow-list.

    Classes that derive (transitively) from a framework base such as
    `MonoBehaviour` are treated as entry points — the framework instantiates
    them, so the absence of an in-project reference is expected. Override the
    base list with the `framework_bases` option.

    Snapshot rule: by default checks every class. If `scope: diff`, only checks
    classes whose status is ADDED or CHANGED (i.e. don't fail on classes that
    were already dangling before the change).
    """

    def check(self, ctx: RuleContext) -> Iterable[Violation]:
        entry_points: list[str] = list(self.options.get("entry_points") or [])
        framework_bases: set[str] = set(
            self.options.get("framework_bases") or _DEFAULT_FRAMEWORK_BASES
        )
        for cls in ctx.project.iter_classes():
            qn = cls.qualified_name
            if self.is_ignored(qn):
                continue
            if self.scope == "diff" and ctx.has_diff:
                if cls.status not in (DiffStatus.ADDED, DiffStatus.CHANGED):
                    continue
            # Skip removed ghost classes — they're already gone.
            if cls.status == DiffStatus.REMOVED:
                continue
            if match_any_glob(qn, entry_points):
                continue
            if match_any_glob(cls.name, entry_points):
                continue
            if _derives_from_framework(cls, ctx, framework_bases):
                continue
            incoming = ctx.incoming_refs.get(qn, set())
            # Self-references don't count as incoming.
            incoming = {ref for ref in incoming if ref != qn}
            if not incoming:
                yield self.emit(
                    qualified_name=qn,
                    message=self.message_for(qualified_name=qn)
                    or f"Class '{qn}' has no incoming references (dangling).",
                    location=cls.location,
                )


def _derives_from_framework(
    cls: Class, ctx: RuleContext, framework_bases: set[str]
) -> bool:
    """True if `cls` derives (directly or transitively through project
    ancestors) from any base name in `framework_bases`."""
    stack: list[str] = list(cls.bases)
    seen: set[str] = set()
    while stack:
        base = stack.pop()
        if base in seen:
            continue
        seen.add(base)
        simple = base.split(".")[-1].split("<")[0]
        if simple in framework_bases:
            return True
        parent = ctx.class_by_qn.get(base)
        if parent is None:
            for parent_qn, candidate in ctx.class_by_qn.items():
                if parent_qn.split(".")[-1] == simple:
                    parent = candidate
                    break
        if parent is not None:
            stack.extend(parent.bases)
    return False
