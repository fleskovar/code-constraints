"""Run the checks and project the result into one keyed issue list.

`cdec exceptions allow V-1A2B3C4D` has to answer "which issue is that?", and the
only honest answer comes from re-running the checks: a key is a hash of an
identity, not a record you can look up. Re-deriving it also means an exception
can never be granted for an issue that isn't actually there — the key must match
something reported *now*, or the command refuses.

Since every gate is a rule, this is one run of the same engine `cdec check`
uses, resolved through `lint.pipeline` with the same options. The keys only line
up if both commands look at the same source and the same baseline, and this is
what guarantees they do.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from code_constraints.lint.config import (
    LoadedRules,
    ProjectConfig,
    load_project_config,
    load_rules,
)
from code_constraints.lint.pipeline import PipelineError, parse_source, resolve_baseline
from code_constraints.waivers.model import Issue
from code_constraints.waivers.store import WaiverStore, ledger_paths, load_waivers


@dataclass
class CollectOptions:
    """Everything that changes *which* issues exist. Mirrors `cdec check`'s
    options one for one, because the keys have to line up with the report the
    reviewer is holding."""

    source: Path | None = None
    reference: Path | None = None
    base_ref: str | None = None
    repo: Path = Path(".")


@dataclass
class Collected:
    issues: list[Issue] = field(default_factory=list)
    store: WaiverStore = field(default_factory=WaiverStore)
    ledger_path: Path = Path()
    config: ProjectConfig | None = None
    # Rule ids whose results in `issues` are complete. `prune` needs this: an
    # exception isn't stale just because the rule that reports it didn't run.
    rules_ran: set[str] = field(default_factory=set)
    # Engines whose results are complete, derived from `rules_ran`. An exception
    # is keyed by engine, so this is the granularity pruning works at.
    engines_ran: set[str] = field(default_factory=set)
    # Rules that couldn't run, with the reason (e.g. a language with no
    # fingerprinter). Reported rather than swallowed: a silently skipped rule
    # looks exactly like a clean one.
    skipped: list[tuple[str, str]] = field(default_factory=list)

    def by_key(self) -> dict[str, Issue]:
        return {issue.key: issue for issue in self.issues}

    def open_issues(self) -> list[Issue]:
        return [i for i in self.issues if not i.waived]


def collect_issues(config_dir: Path, options: CollectOptions | None = None) -> Collected:
    """Every issue `cdec check` currently reports, accepted ones included.

    Accepted issues stay in the list (flagged `waived=True`) so `remove` and
    `prune` can reason about them.
    """
    opts = options or CollectOptions()
    cfg = load_project_config(config_dir)
    source_path = opts.source.resolve() if opts.source else cfg.source
    rules_file, _ = ledger_paths(config_dir)
    store = load_waivers(config_dir)

    out = Collected(store=store, ledger_path=rules_file, config=cfg)

    head_proj = parse_source(source_path, cfg.language)
    annotated, has_diff, base_proj = resolve_baseline(
        head_proj=head_proj,
        lang=cfg.language,
        config_dir=config_dir,
        explicit_reference=opts.reference,
        explicit_base_ref=opts.base_ref,
        repo_path=opts.repo,
        default_reference=cfg.reference,
    )

    # Imported here, not at module scope: `lint.engine` pulls in `lint.baseline`,
    # which adapts this package's store — a module-level import would close the
    # cycle while `waivers` is still initialising.
    from code_constraints.lint.engine import SourceContext, run_checks

    loaded: LoadedRules = load_rules(config_dir)
    # Run unfiltered (`baseline=None`) so accepted issues are still visible to
    # the review workflow rather than silently dropped.
    report = run_checks(
        annotated,
        loaded.rules,
        has_diff=has_diff,
        baseline=None,
        baseline_project=base_proj,
        source_context=SourceContext(
            source=source_path,
            language=cfg.language,
            config_dir=config_dir,
            reference_path=opts.reference or cfg.reference_path,
        ),
    )

    skipped_ids = {rule_id for rule_id, _ in report.skipped}
    out.skipped = list(report.skipped)
    for rule in loaded.rules:
        if rule.rule_id not in skipped_ids:
            out.rules_ran.add(rule.rule_id)

    for v in report.violations:
        issue = Issue(
            engine=v.key_engine,
            rule=v.key_rule or v.rule_id,
            rule_id=v.rule_id,
            qualified_name=v.qualified_name,
            detail=v.signature or "",
            message=v.message,
            severity=v.severity.value,
            file=v.location.file if v.location else "",
            line=v.location.start_line if v.location else 0,
            waivable=v.waivable,
        )
        out.issues.append(issue)
        out.engines_ran.add(issue.engine)

    # A rule that ran and found nothing still counts as "this engine ran", which
    # is exactly the case where a stale exception should be pruned.
    for rule in loaded.rules:
        if rule.rule_id in skipped_ids:
            continue
        out.engines_ran.update(_engines_of(rule))

    for issue in out.issues:
        if issue.waivable and store.has(issue.key):
            issue.waived = True
            waiver = store.get(issue.key)
            issue.waiver_reason = waiver.reason if waiver else ""

    return out


def _engines_of(rule) -> set[str]:
    """Which key-engine(s) a rule type can produce issues under.

    Needed because pruning happens per engine but a clean run reports no
    violations to read the engine off, and dropping every `F-` exception just
    because the tag-conformance rule happened to pass would be wrong only if
    that rule never ran at all.
    """
    return {
        "tag-conformance": {"enforce"},
        "implementation-locks": {"lock"},
        "reference-architecture": {"reference"},
    }.get(rule.type_name, {"check"})


__all__ = ["CollectOptions", "Collected", "collect_issues", "PipelineError"]
