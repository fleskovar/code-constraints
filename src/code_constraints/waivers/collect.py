"""Run every engine and project the results into one keyed issue list.

`cdec baseline allow V-1A2B3C4D` has to answer "which issue is that?", and the
only honest answer comes from re-running the checks: a key is a hash of an
identity, not a record you can look up. Re-deriving it also means a waiver can
never be granted for an issue that isn't actually there — the key must match
something the engines report *now*, or the command refuses.

The engines are invoked through their public entry points and adapted here, so
this module is the only place that knows about all three. They still don't know
about each other.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from code_constraints.lint.config import (
    BASELINE_FILENAME,
    LoadedRules,
    ProjectConfig,
    load_project_config,
    load_rules,
)
from code_constraints.lint.pipeline import PipelineError, parse_source, resolve_baseline
from code_constraints.waivers.model import Issue
from code_constraints.waivers.store import WaiverStore, load_waivers


@dataclass
class CollectOptions:
    """Everything that changes *which* issues exist. Mirrors `cdec check`'s
    options one for one, because the keys have to line up with the report the
    reviewer is holding."""

    source: Path | None = None
    reference: Path | None = None
    base_ref: str | None = None
    repo: Path = Path(".")
    include_enforce: bool = True
    include_locks: bool = True


@dataclass
class Collected:
    issues: list[Issue] = field(default_factory=list)
    store: WaiverStore = field(default_factory=WaiverStore)
    baseline_path: Path = Path()
    config: ProjectConfig | None = None
    # Engines whose results in `issues` are complete. `prune` needs this: a
    # waiver isn't stale just because the engine that reports it didn't run.
    engines_ran: set[str] = field(default_factory=set)
    # Engines that couldn't run, with the reason (e.g. a language with no
    # fingerprinter). Reported rather than swallowed: a silently skipped engine
    # looks exactly like a clean one.
    skipped: list[tuple[str, str]] = field(default_factory=list)

    def by_key(self) -> dict[str, Issue]:
        return {issue.key: issue for issue in self.issues}

    def open_issues(self) -> list[Issue]:
        return [i for i in self.issues if not i.waived]


def collect_issues(config_dir: Path, options: CollectOptions | None = None) -> Collected:
    """Every issue the three engines currently report, waived ones included.

    Waived issues stay in the list (flagged `waived=True`) so `remove` and
    `prune` can reason about them.
    """
    opts = options or CollectOptions()
    cfg = load_project_config(config_dir)
    source_path = opts.source.resolve() if opts.source else cfg.source
    baseline_path = config_dir / BASELINE_FILENAME
    store = load_waivers(baseline_path)

    out = Collected(store=store, baseline_path=baseline_path, config=cfg)

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

    # ---- Engine A: architectural drift. Run unfiltered so waived issues are
    # still visible to the review workflow.
    # Imported here, not at module scope: `lint.engine` pulls in `lint.baseline`,
    # which adapts this package's store — a module-level import would close the
    # cycle while `waivers` is still initialising.
    from code_constraints.lint.engine import run_checks

    loaded: LoadedRules = load_rules(config_dir)
    out.engines_ran.add("check")
    report = run_checks(
        annotated, loaded.rules, has_diff=has_diff, baseline=None,
        baseline_project=base_proj,
    )
    for rule_id, reason in report.skipped:
        out.skipped.append((f"check/{rule_id}", reason))
    for v in report.violations:
        out.issues.append(
            Issue(
                engine="check",
                rule=v.rule_id,
                qualified_name=v.qualified_name,
                detail=v.signature or "",
                message=v.message,
                severity=v.severity.value,
                file=v.location.file if v.location else "",
                line=v.location.start_line if v.location else 0,
            )
        )

    # ---- Engine B: implementation conformance.
    if opts.include_enforce:
        from code_constraints.enforce import enforce as run_enforce

        try:
            findings = run_enforce(source_path, cfg.language)
        except ValueError as exc:
            out.skipped.append(("enforce", str(exc)))
            findings = []
        else:
            out.engines_ran.add("enforce")
        for f in findings:
            out.issues.append(
                Issue(
                    engine="enforce",
                    rule=f.rule,
                    qualified_name=f.qualified_name,
                    detail=f.detail,
                    message=f.message,
                    file=f.file,
                    line=f.line,
                )
            )

    # ---- Engine C: frozen implementations. Listed for visibility only — these
    # are never waivable through the baseline.
    if opts.include_locks and cfg.lock.enabled:
        from code_constraints.lock import (
            LockOptions,
            UnsupportedLockLanguage,
            check_locks,
            load_locks,
        )
        from code_constraints.lint.config import LOCKS_FILENAME

        lock_path = cfg.lock.lockfile or (config_dir / LOCKS_FILENAME)
        lock_options = LockOptions(
            include_docstrings=cfg.lock.include_docstrings,
            patterns=list(cfg.lock.targets),
        )
        try:
            entries = load_locks(lock_path)
            lock_report = check_locks(source_path, cfg.language, entries, lock_options)
        except UnsupportedLockLanguage as exc:
            out.skipped.append(("lock", str(exc)))
        else:
            for lv in lock_report.violations:
                out.issues.append(
                    Issue(
                        engine="lock",
                        rule=lv.kind,
                        qualified_name=lv.target,
                        message=lv.message,
                        file=lv.file,
                        line=lv.line,
                    )
                )

    for issue in out.issues:
        if issue.waivable and store.has(issue.key):
            issue.waived = True
            waiver = store.get(issue.key)
            issue.waiver_reason = waiver.reason if waiver else ""

    return out


__all__ = ["CollectOptions", "Collected", "collect_issues", "PipelineError"]
