"""Orchestrate: build RuleContext, dispatch to rules, collect violations.

This is the whole of `cdec check`. Every gate the tool offers — configured
architectural rules, source-tag conformance, implementation locks, the
reference gate — arrives here as a `Rule`, so there is one run, one report, one
exit code, and one place to grant an exception.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from code_constraints.core.associations import resolve_association
from code_constraints.core.model import DiffStatus, Package, Project

from code_constraints.lint.baseline import Baseline
from code_constraints.lint.report import Report
from code_constraints.lint.rules.base import Rule, RuleContext, RuleSkipped, Violation


@dataclass
class SourceContext:
    """Where the code and the config live.

    Needed only by the rules that adapt an engine which re-reads the source
    (tag conformance, locks) or loads a second model (the reference gate).
    Rules that read the model alone never touch it, which is why it is optional.
    """

    source: Path | None = None
    language: str = ""
    config_dir: Path | None = None
    reference_path: Path | None = None


def run_checks(
    project: Project,
    rules: Iterable[Rule],
    *,
    has_diff: bool,
    baseline: Baseline | None = None,
    baseline_project: Project | None = None,
    source_context: SourceContext | None = None,
    bypass_locks: bool = False,
    bypass_reason: str = "",
) -> Report:
    """Run every rule and return a `Report`.

    `project` is the annotated `Project` when `has_diff` is True (i.e. the
    output of `diff_projects`); when `has_diff` is False it's a raw parse and
    every element has `DiffStatus.UNCHANGED`.

    `baseline_project` is the OLD side of the diff (unannotated). Diff-scope
    rules that need the previous element state (e.g. frozen-rules) read it via
    `ctx.baseline_class_by_qn`.

    `bypass_locks` moves lock violations out of the failing set into
    `Report.bypassed`. They are still collected and still printed under an audit
    banner, and the JSON report says so, so a pipeline can reject a bypassed run
    on a protected branch rather than silently accepting it.
    """
    ctx = _build_context(project, has_diff, baseline_project, source_context)
    raw: list[Violation] = []
    skipped: list[tuple[str, str]] = []
    for rule in rules:
        if rule.scope == "diff" and not has_diff:
            skipped.append((rule.rule_id, "no baseline available; diff-scope rule skipped"))
            continue
        try:
            # Materialised inside the guard: `check` is a generator in most
            # rules, so a RuleSkipped raised in its body only surfaces on
            # iteration.
            raw.extend(rule.check(ctx) or ())
        except RuleSkipped as exc:
            skipped.append((rule.rule_id, str(exc)))
    if baseline is not None:
        kept, suppressed = baseline.filter(raw)
    else:
        kept, suppressed = raw, []
    bypassed: list[Violation] = []
    if bypass_locks:
        held = [v for v in kept if v.key_engine == "lock"]
        if held:
            kept = [v for v in kept if v.key_engine != "lock"]
            bypassed = held
    return Report(
        violations=kept,
        suppressed=suppressed,
        skipped=skipped,
        bypassed=bypassed,
        bypass_reason=bypass_reason if bypassed else "",
    )


def _build_context(
    project: Project,
    has_diff: bool,
    baseline_project: Project | None = None,
    source_context: SourceContext | None = None,
) -> RuleContext:
    src = source_context or SourceContext()
    ctx = RuleContext(
        project=project,
        has_diff=has_diff,
        source=src.source,
        language=src.language,
        config_dir=src.config_dir,
        reference_path=src.reference_path,
    )
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
