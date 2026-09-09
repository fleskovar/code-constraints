"""Orchestrate: build RuleContext, dispatch to rules, collect violations."""

from __future__ import annotations

from typing import Iterable

from code_constraints.core.associations import resolve_association
from code_constraints.core.model import DiffStatus, Package, Project

from code_constraints.lint.baseline import Baseline
from code_constraints.lint.report import Report
from code_constraints.lint.rules.base import Rule, RuleContext, Violation


def run_checks(
    project: Project,
    rules: Iterable[Rule],
    *,
    has_diff: bool,
    baseline: Baseline | None = None,
    baseline_project: Project | None = None,
) -> Report:
    """Run every rule and return a `Report`.

    `project` is the annotated `Project` when `has_diff` is True (i.e. the
    output of `diff_projects`); when `has_diff` is False it's a raw parse and
    every element has `DiffStatus.UNCHANGED`.

    `baseline_project` is the OLD side of the diff (unannotated). Diff-scope
    rules that need the previous element state (e.g. frozen-rules) read it via
    `ctx.baseline_class_by_qn`.
    """
    ctx = _build_context(project, has_diff, baseline_project)
    raw: list[Violation] = []
    skipped: list[tuple[str, str]] = []
    for rule in rules:
        if rule.scope == "diff" and not has_diff:
            skipped.append((rule.rule_id, "no baseline available; diff-scope rule skipped"))
            continue
        for v in rule.check(ctx) or ():
            raw.append(v)
    if baseline is not None:
        kept, suppressed = baseline.filter(raw)
    else:
        kept, suppressed = raw, []
    return Report(violations=kept, suppressed=suppressed, skipped=skipped)


def _build_context(
    project: Project, has_diff: bool, baseline_project: Project | None = None
) -> RuleContext:
    ctx = RuleContext(project=project, has_diff=has_diff)
    # Class index by qualified name.
    for cls in project.iter_classes():
        ctx.class_by_qn[cls.qualified_name] = cls
    if baseline_project is not None:
        for cls in baseline_project.iter_classes():
            ctx.baseline_class_by_qn[cls.qualified_name] = cls
    # Map class -> containing package.
    for pkg in _walk_packages(project.packages):
        for cls in pkg.classes:
            ctx.class_to_package[cls.qualified_name] = pkg.qualified_name

    # Outgoing references (attribute types + bases that resolve to project classes).
    for cls in project.iter_classes():
        if cls.status == DiffStatus.REMOVED:
            continue
        outgoing: set[str] = set()
        for attr in cls.attributes:
            if attr.status == DiffStatus.REMOVED:
                continue
            target_qn, _ = resolve_association(attr.type, project)
            if target_qn:
                outgoing.add(target_qn)
        # Usage references: method parameter / return types and types used
        # inside method bodies. Mirrors graph_model so the dangling rule and the
        # diagram agree on what "references" a class.
        for op in cls.operations:
            if op.status == DiffStatus.REMOVED:
                continue
            for raw_type in (op.return_type, *(p.type for p in op.parameters)):
                target_qn, _ = resolve_association(raw_type, project)
                if target_qn:
                    outgoing.add(target_qn)
        for dep in cls.dependencies:
            target_qn, _ = resolve_association(dep, project)
            if target_qn:
                outgoing.add(target_qn)
        for base in cls.bases:
            if base in ctx.class_by_qn:
                outgoing.add(base)
                continue
            # Fall back to short-name match (mirrors graph_model logic).
            short = base.split(".")[-1]
            for qn in ctx.class_by_qn:
                if qn.split(".")[-1] == short:
                    outgoing.add(qn)
                    break
        ctx.outgoing_refs[cls.qualified_name] = outgoing
        for tgt in outgoing:
            ctx.incoming_refs.setdefault(tgt, set()).add(cls.qualified_name)

    # Aggregate to package level.
    for src_qn, tgt_qns in ctx.outgoing_refs.items():
        src_pkg = ctx.class_to_package.get(src_qn)
        if src_pkg is None:
            continue
        bucket = ctx.outgoing_pkg_refs.setdefault(src_pkg, set())
        for tgt_qn in tgt_qns:
            tgt_pkg = ctx.class_to_package.get(tgt_qn)
            if tgt_pkg is None or tgt_pkg == src_pkg:
                continue
            bucket.add(tgt_pkg)
    return ctx


def _walk_packages(packages: list[Package]):
    for pkg in packages:
        yield pkg
        yield from _walk_packages(pkg.sub_packages)
