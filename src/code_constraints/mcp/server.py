"""The MCP tool surface over code-constraints.

Every tool calls the library in-process rather than shelling out to `cdec`, for
two reasons: results come back as structured JSON instead of human text, and the
issue keys (`V-`/`F-`/`L-`) are derived by exactly the same code path the CLI
uses — so a key an agent reads from `cdec_check` is the same key
`cdec baseline allow` accepts on the command line.

Path arguments are resolved against the server's project root (`--project-root`,
`$CDEC_PROJECT_ROOT`, else the process CWD), so an agent can pass repo-relative
paths without knowing where the harness launched the server.

**stdout is the MCP transport.** Nothing in this module may print — the engines
are all called as libraries (the CLI's `typer.echo` reporting is reimplemented
here as return values) and logging is pinned to stderr in `__main__`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Optional
from urllib.parse import quote

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from code_constraints.lint.config import (
    BASELINE_FILENAME,
    LOCKS_FILENAME,
    REFERENCE_FILENAME,
    ConfigError,
    load_project_config,
    load_rules,
)

if TYPE_CHECKING:
    # Annotation-only: the engines are imported lazily inside each tool so that
    # building the server (which every harness does at startup) stays cheap.
    from code_constraints.core.model import Project
    from code_constraints.lock import LockEntry, LockOptions
    from code_constraints.waivers import ApplyResult, Collected, Issue, WaiverStore

Language = Literal[
    "python", "csharp", "typescript", "svelte", "odin", "lua", "julia"
]

SERVER_INSTRUCTIONS = """\
code-constraints (`cdec`) enforces architectural and implementation constraints \
on a codebase. Three decoupled engines answer three different questions:

  * `cdec_check`      (Engine A) — did the architecture DRIFT from the reference?
  * `cdec_enforce`    (Engine B) — does the code OBEY its rule tags right now?
  * `cdec_lock_check` (Engine C) — did a frozen implementation CHANGE at all?

Typical flows:

  Gate a change      -> cdec_check(enforce=True). It runs A + B + C together.
  Triage everything  -> cdec_issues, which returns one keyed list across engines.
  Accept a violation -> cdec_allow(keys=["V-1A2B3C4D"], reason="why").
                        Locks are NOT waivable; re-baseline with
                        cdec_lock_set(force=True) instead, which leaves a
                        reviewable diff on .cdec/locks.yaml.
  Agree a design     -> write a model .json, cdec_propose it (the browser shows
                        it diffed against the code), iterate, then
                        cdec_reference_set to lock it as the target.

Every issue carries a stable key derived from its identity, never from a file
offset: re-running over unchanged code returns the same keys, and inserting
lines above an element does not move them.
"""


# --------------------------------------------------------------------------
# root / path resolution
# --------------------------------------------------------------------------

@dataclass
class _Roots:
    """Where the server resolves relative paths from."""

    project_root: Path

    def path(self, value: str | None, default: Path | None = None) -> Path | None:
        """Resolve a caller-supplied path against the project root."""
        if value is None:
            return default
        p = Path(value).expanduser()
        return (p if p.is_absolute() else self.project_root / p).resolve()

    def config_dir(self, value: str | None) -> Path:
        resolved = self.path(value, self.project_root / ".cdec")
        assert resolved is not None  # default is non-None
        return resolved

    def require_dir(self, value: str | None, *, what: str) -> Path:
        p = self.path(value)
        if p is None:
            raise ToolError(f"{what} is required")
        if not p.is_dir():
            raise ToolError(f"{what} is not a directory: {p}")
        return p

    def require_file(self, value: str | None, *, what: str) -> Path:
        p = self.path(value)
        if p is None:
            raise ToolError(f"{what} is required")
        if not p.is_file():
            raise ToolError(f"{what} not found: {p}")
        return p


def _rel(roots: _Roots, path: Path) -> str:
    """Render a path relative to the project root when it lives inside it, so
    tool output reads like the repo the agent is working in."""
    try:
        return str(path.relative_to(roots.project_root)).replace("\\", "/")
    except ValueError:
        return str(path)


def _resolve_inputs(
    roots: _Roots,
    source: str | None,
    lang: str | None,
    reference: str | None,
    config_dir: str | None,
) -> tuple[Path, str, Path, Path]:
    """(source, language, reference_path, config_dir), with `.cdec/` filling gaps.

    Mirrors the CLI's `_resolve_reference_inputs` so a tool call and the
    equivalent `cdec` invocation see identical inputs.
    """
    from code_constraints.cli.detect import detect_language

    cfg_dir = roots.config_dir(config_dir)
    cfg = None
    try:
        cfg = load_project_config(cfg_dir)
    except ConfigError:
        cfg = None

    source_path = roots.path(source) or (cfg.source if cfg else None)
    if source_path is None:
        raise ToolError(
            f"no source given and none found in {_rel(roots, cfg_dir / 'config.yaml')}; "
            "pass `source`, or scaffold the project with `cdec init`."
        )
    if not source_path.is_dir():
        raise ToolError(f"source is not a directory: {source_path}")

    chosen = lang or (cfg.language if cfg else None) or detect_language(source_path)
    if chosen is None:
        raise ToolError(
            f"could not determine a language for {_rel(roots, source_path)}; pass `lang`."
        )
    if chosen not in (
        "python", "csharp", "typescript", "svelte", "odin", "lua", "julia",
    ):
        raise ToolError(f"unsupported language: {chosen}")

    ref = roots.path(reference)
    if ref is None:
        ref = (cfg.reference if cfg and cfg.reference else cfg_dir / REFERENCE_FILENAME)
    return source_path, chosen, ref, cfg_dir


def _parse(source: Path, lang: str) -> "Project":
    from code_constraints.lint.pipeline import PipelineError, parse_source

    try:
        return parse_source(source, lang)
    except PipelineError as exc:
        raise ToolError(str(exc)) from exc


def _load_model(path: Path) -> "Project":
    from code_constraints.core.model_io import UnsupportedModelFormat, load_model

    try:
        return load_model(path)
    except UnsupportedModelFormat as exc:
        raise ToolError(str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - surfaced verbatim
        raise ToolError(f"could not read model {path}: {exc}") from exc


def _count_classes(project: "Project") -> int:
    """How many classes a model holds — the one number worth echoing back after
    a write, so a caller can tell an empty parse from a real one.

    `iter_classes` is untyped, so count through a list rather than `sum` over a
    generator — mypy resolves the latter to the `Iterable[bool]` overload.
    """
    return len(list(project.iter_classes()))  # type: ignore[no-untyped-call]


def _save_model(project: "Project", path: Path) -> None:
    from code_constraints.core.model_io import UnsupportedModelFormat, save_model

    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        save_model(project, path)
    except UnsupportedModelFormat as exc:
        raise ToolError(str(exc)) from exc


def _lock_inputs(
    roots: _Roots, source: Path, lang: str, cfg_dir: Path, lockfile: str | None
) -> tuple[Path, dict[str, "LockEntry"], "LockOptions"]:
    """(lockfile_path, entries, LockOptions) resolved like the CLI's `_lock_context`."""
    from code_constraints.lock import LockOptions, LockfileError, load_locks

    cfg = None
    try:
        cfg = load_project_config(cfg_dir)
    except ConfigError:
        cfg = None

    path = roots.path(lockfile)
    if path is None:
        path = (
            cfg.lock.lockfile
            if cfg is not None and cfg.lock.lockfile is not None
            else cfg_dir / LOCKS_FILENAME
        )
    options = LockOptions(
        include_docstrings=cfg.lock.include_docstrings if cfg else False,
        patterns=list(cfg.lock.targets) if cfg else [],
    )
    try:
        entries = load_locks(path)
    except LockfileError as exc:
        raise ToolError(str(exc)) from exc
    return path, entries, options


def _collect(
    roots: _Roots, config_dir: str | None, **opts: Any
) -> tuple[Path, "Collected"]:
    """Run all three engines and return the keyed `Collected` issue list."""
    from code_constraints.lint.pipeline import PipelineError
    from code_constraints.waivers import CollectOptions, collect_issues
    from code_constraints.waivers.store import WaiverFileError

    cfg_dir = roots.config_dir(config_dir)
    try:
        return cfg_dir, collect_issues(
            cfg_dir,
            CollectOptions(
                source=roots.path(opts.get("source")),
                reference=roots.path(opts.get("reference")),
                base_ref=opts.get("base_ref"),
                repo=roots.path(opts.get("repo")) or roots.project_root,
            ),
        )
    except (ConfigError, PipelineError, WaiverFileError) as exc:
        raise ToolError(str(exc)) from exc


def _issue_json(issue: "Issue") -> dict[str, Any]:
    return {
        "key": issue.key,
        "engine": issue.engine,
        "rule": issue.rule,
        "qualified_name": issue.qualified_name,
        "detail": issue.detail,
        "message": issue.message,
        "severity": issue.severity,
        "file": issue.file,
        "line": issue.line,
        "waived": issue.waived,
        "waiver_reason": issue.waiver_reason,
        "waivable": issue.waivable,
    }


def _apply_result_json(result: "ApplyResult") -> dict[str, Any]:
    return {
        "allowed": [_issue_json(i) for i in result.allowed],
        "already_waived": [i.key for i in result.already_waived],
        "removed": [w.key for w in result.removed],
        "unknown": list(result.unknown),
        "refused": [{"key": k, "reason": why} for k, why in result.refused],
        "not_waived": list(result.not_waived),
        "malformed": list(result.malformed),
        "problems": list(result.problems),
        "changed": result.changed,
        "failed": result.failed,
    }


# --------------------------------------------------------------------------
# server construction
# --------------------------------------------------------------------------

def build_server(project_root: Path | None = None) -> MCPServer:
    """Build the code-constraints MCP server.

    `project_root` anchors every relative path a tool receives. It defaults to
    `$CDEC_PROJECT_ROOT` and then to the process working directory, which is
    what most harnesses set to the open workspace.
    """
    root = (
        project_root
        or (Path(os.environ["CDEC_PROJECT_ROOT"]) if os.environ.get("CDEC_PROJECT_ROOT") else None)
        or Path.cwd()
    ).expanduser().resolve()
    roots = _Roots(project_root=root)

    mcp = MCPServer(
        name="code-constraints",
        title="code-constraints",
        version=_package_version(),
        instructions=SERVER_INSTRUCTIONS,
    )

    # ---------------------------------------------------------------- context

    @mcp.tool()
    def cdec_status(config_dir: Optional[str] = None) -> dict[str, Any]:
        """Show how code-constraints is configured for this project.

        Start here when you don't know whether a repo uses cdec, which engines
        are active, or where its reference model and ledgers live.
        """
        cfg_dir = roots.config_dir(config_dir)
        out: dict[str, Any] = {
            "project_root": str(roots.project_root),
            "config_dir": _rel(roots, cfg_dir),
            "configured": False,
        }
        try:
            cfg = load_project_config(cfg_dir)
        except ConfigError as exc:
            out["error"] = str(exc)
            out["hint"] = "Run `cdec init` in the project to scaffold `.cdec/`."
            return out

        ref = cfg.reference or (cfg_dir / REFERENCE_FILENAME)
        baseline_path = cfg_dir / BASELINE_FILENAME
        lock_path = cfg.lock.lockfile or (cfg_dir / LOCKS_FILENAME)

        n_rules = 0
        rules_error = None
        try:
            n_rules = len(load_rules(cfg_dir).rules)
        except ConfigError as exc:
            rules_error = str(exc)

        n_waivers = 0
        try:
            from code_constraints.waivers import load_waivers

            n_waivers = len(load_waivers(baseline_path).waivers)
        except Exception as exc:  # noqa: BLE001 - reported, not fatal
            out["baseline_error"] = str(exc)

        n_locks = 0
        try:
            from code_constraints.lock import load_locks

            n_locks = len(load_locks(lock_path))
        except Exception as exc:  # noqa: BLE001 - reported, not fatal
            out["lockfile_error"] = str(exc)

        out.update(
            {
                "configured": True,
                "language": cfg.language,
                "source": _rel(roots, cfg.source),
                "reference": {"path": _rel(roots, ref), "exists": ref.is_file()},
                "rules": {"count": n_rules, "error": rules_error},
                "waivers": {"path": _rel(roots, baseline_path), "count": n_waivers},
                "locks": {
                    "enabled": cfg.lock.enabled,
                    "path": _rel(roots, lock_path),
                    "count": n_locks,
                    "targets": list(cfg.lock.targets),
                    "include_docstrings": cfg.lock.include_docstrings,
                },
            }
        )
        return out

    @mcp.tool()
    def cdec_rules() -> dict[str, Any]:
        """List the architectural rule tags that can be applied to code.

        These are the decorators/attributes (`@no_instantiation`, `[Sealed]`, …)
        that Engines A and B read. Use this before adding a tag so you use the
        real name, its legal targets, and its parameters.
        """
        from code_constraints.core.rules import (
            CSHARP_SHIM_NAMESPACE,
            PYTHON_SHIM_MODULES,
            RULE_CATALOG,
        )

        return {
            "shims": {
                "python_import": sorted(PYTHON_SHIM_MODULES),
                "csharp_using": CSHARP_SHIM_NAMESPACE,
                "note": (
                    "A tag is only recognised when imported from the shim namespace, "
                    "so unrelated decorators never false-match."
                ),
            },
            "rules": [
                {
                    "id": spec.id,
                    "python": f"@{spec.python_name}",
                    "csharp": f"[{spec.csharp_name}]",
                    "targets": sorted(spec.targets),
                    "params": list(spec.params),
                    "enforcement": spec.enforcement,
                    "summary": spec.summary,
                }
                for spec in RULE_CATALOG.values()
            ],
        }

    # ------------------------------------------------------------ the engines

    @mcp.tool()
    def cdec_check(
        config_dir: Optional[str] = None,
        source: Optional[str] = None,
        reference: Optional[str] = None,
        base_ref: Optional[str] = None,
        repo: Optional[str] = None,
        enforce: bool = False,
        locks: bool = True,
        fail_on: Literal["error", "warning", "none"] = "error",
    ) -> dict[str, Any]:
        """Engine A: check the architecture for drift against the reference model.

        Runs the `.cdec/rules.yaml` rule set over the parsed model — it never
        reads method bodies. Set `enforce=True` to also run Engine B, and leave
        `locks=True` so a frozen implementation is verified by the same call CI
        makes. `base_ref` diffs against a git revision instead of the reference
        XMI; diff-scope rules are skipped (and reported in `skipped`) when
        neither baseline is available.

        `ok` is the pass/fail verdict. Every violation carries a `key` that
        `cdec_allow` accepts.
        """
        from code_constraints.lint.baseline import load_baseline
        from code_constraints.lint.engine import run_checks
        from code_constraints.lint.pipeline import PipelineError, resolve_baseline
        from code_constraints.lint.rules.base import Severity

        cfg_dir = roots.config_dir(config_dir)
        try:
            cfg = load_project_config(cfg_dir)
            loaded = load_rules(cfg_dir)
        except ConfigError as exc:
            raise ToolError(str(exc)) from exc

        source_path = roots.path(source) or cfg.source
        head = _parse(source_path, cfg.language)
        try:
            annotated, has_diff, base_proj = resolve_baseline(
                head_proj=head,
                lang=cfg.language,
                config_dir=cfg_dir,
                explicit_reference=roots.path(reference),
                explicit_base_ref=base_ref,
                repo_path=roots.path(repo) or roots.project_root,
                default_reference=cfg.reference,
            )
        except PipelineError as exc:
            raise ToolError(str(exc)) from exc

        baseline = load_baseline(cfg_dir / BASELINE_FILENAME)
        report = run_checks(
            annotated,
            loaded.rules,
            has_diff=has_diff,
            baseline=baseline,
            baseline_project=base_proj,
        )

        out: dict[str, Any] = {
            "source": _rel(roots, source_path),
            "language": cfg.language,
            "has_baseline": has_diff,
            "check": report.to_json(),
            "text": report.to_human(),
        }
        failed = report.has_failures(Severity(fail_on))

        if enforce:
            from code_constraints.enforce import enforce as run_enforce
            from code_constraints.enforce import findings_to_json, format_findings

            findings = run_enforce(source_path, cfg.language)
            kept = [
                f
                for f in findings
                if not baseline.store.matches("enforce", f.rule, f.qualified_name, f.detail)
            ]
            silenced = len(findings) - len(kept)
            out["enforce"] = {
                "findings": findings_to_json(kept),
                "suppressed": silenced,
            }
            out["text"] += format_findings(kept, suppressed=silenced)
            failed = failed or bool(kept)

        if locks and cfg.lock.enabled:
            from code_constraints.lock import UnsupportedLockLanguage, check_locks
            from code_constraints.lock import format_report as format_lock_report
            from code_constraints.lock import report_to_json as lock_report_to_json

            lock_path, entries, options = _lock_inputs(
                roots, source_path, cfg.language, cfg_dir, None
            )
            opted_in = bool(entries or options.patterns)
            try:
                lock_report = check_locks(source_path, cfg.language, entries, options)
            except UnsupportedLockLanguage as exc:
                if opted_in:
                    raise ToolError(str(exc)) from exc
                lock_report = None
            if lock_report is not None and (
                lock_report.checked or lock_report.declared or lock_report.violations
            ):
                out["locks"] = lock_report_to_json(lock_report)
                out["text"] += format_lock_report(lock_report)
                failed = failed or not lock_report.ok

        out["ok"] = not failed
        return out

    @mcp.tool()
    def cdec_enforce(
        source: Optional[str] = None,
        lang: Optional[str] = None,
        config_dir: Optional[str] = None,
        include_waived: bool = False,
    ) -> dict[str, Any]:
        """Engine B: check that implementations obey their rule tags.

        Re-parses the source and inspects method bodies for `no-instantiation`,
        `factory` and `immutable`, plus the structural `sealed` rule. Fully
        independent of the reference model and the diff. Findings already
        accepted into `.cdec/baseline.yaml` are silenced unless
        `include_waived=True`.
        """
        from code_constraints.enforce import enforce as run_enforce
        from code_constraints.enforce import findings_to_json, format_findings

        source_path, chosen, _ref, cfg_dir = _resolve_inputs(
            roots, source, lang, None, config_dir
        )
        try:
            findings = run_enforce(source_path, chosen)
        except ValueError as exc:
            raise ToolError(str(exc)) from exc

        suppressed = 0
        if not include_waived:
            from code_constraints.waivers import load_waivers

            store = load_waivers(cfg_dir / BASELINE_FILENAME)
            kept = [
                f
                for f in findings
                if not store.matches("enforce", f.rule, f.qualified_name, f.detail)
            ]
            suppressed = len(findings) - len(kept)
            findings = kept

        return {
            "ok": not findings,
            "source": _rel(roots, source_path),
            "language": chosen,
            "findings": findings_to_json(findings),
            "suppressed": suppressed,
            "text": format_findings(findings, suppressed=suppressed),
        }

    @mcp.tool()
    def cdec_lock_check(
        source: Optional[str] = None,
        lang: Optional[str] = None,
        config_dir: Optional[str] = None,
        lockfile: Optional[str] = None,
    ) -> dict[str, Any]:
        """Engine C: verify that frozen (`@locked`) implementations are unchanged.

        A lock is an AST identity, not a line range, so moving or reformatting
        code around a locked element never trips it. Catches five things: an
        edited body, a deleted element, a deleted tag, a tag that was never
        baselined, and a digest-algorithm change.

        Lock violations are NOT waivable. Accepting one means
        `cdec_lock_set(force=True)`, which leaves a reviewable ledger diff.
        """
        from code_constraints.lock import UnsupportedLockLanguage, check_locks, format_report
        from code_constraints.lock import report_to_json

        source_path, chosen, _ref, cfg_dir = _resolve_inputs(
            roots, source, lang, None, config_dir
        )
        lock_path, entries, options = _lock_inputs(roots, source_path, chosen, cfg_dir, lockfile)
        try:
            report = check_locks(source_path, chosen, entries, options)
        except UnsupportedLockLanguage as exc:
            raise ToolError(str(exc)) from exc

        payload = report_to_json(report)
        payload.update(
            {
                "ok": report.ok,
                "lockfile": _rel(roots, lock_path),
                "text": format_report(report),
            }
        )
        return payload

    @mcp.tool()
    def cdec_lock_list(
        source: Optional[str] = None,
        lang: Optional[str] = None,
        config_dir: Optional[str] = None,
        lockfile: Optional[str] = None,
    ) -> dict[str, Any]:
        """List which elements are lockable, which are tagged, and which are frozen.

        Use it to see what a `@locked` / `[Locked]` tag would cover before you
        baseline it, and to spot tags that have never been recorded in the ledger.
        """
        from code_constraints.lock import UnsupportedLockLanguage, collect_targets, is_locked_target

        source_path, chosen, _ref, cfg_dir = _resolve_inputs(
            roots, source, lang, None, config_dir
        )
        lock_path, entries, options = _lock_inputs(roots, source_path, chosen, cfg_dir, lockfile)
        try:
            targets = collect_targets(source_path, chosen, options)
        except UnsupportedLockLanguage as exc:
            raise ToolError(str(exc)) from exc

        rows = []
        for t in targets:
            entry = entries.get(t.target)
            rows.append(
                {
                    "target": t.target,
                    "kind": t.kind,
                    "file": t.file,
                    "line": t.line,
                    "tagged": is_locked_target(t, options.patterns),
                    "baselined": entry is not None,
                    "digest": entry.digest if entry else None,
                }
            )
        stale = [name for name in entries if name not in {t.target for t in targets}]
        return {
            "lockfile": _rel(roots, lock_path),
            "targets": rows,
            "stale_entries": stale,
            "summary": {
                "lockable": len(rows),
                "tagged": sum(1 for r in rows if r["tagged"]),
                "baselined": sum(1 for r in rows if r["baselined"]),
                "stale": len(stale),
            },
        }

    @mcp.tool()
    def cdec_lock_set(
        source: Optional[str] = None,
        lang: Optional[str] = None,
        config_dir: Optional[str] = None,
        lockfile: Optional[str] = None,
        target: Optional[list[str]] = None,
        force: bool = False,
        reason: str = "",
        owner: str = "",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Record current implementations as the approved locked baseline.

        Without `force` this only ADDS locks for newly tagged elements — it can
        never erase evidence that frozen code changed, so it is always safe to
        run. `force=True` is the privileged operation: it re-baselines drifted
        implementations and prunes stale entries, i.e. it ACCEPTS a change to
        frozen code. Only use it when the user has explicitly approved that
        change; it is meant to show up as a reviewable `.cdec/locks.yaml` diff.
        """
        from code_constraints.lock import update_locks, write_locks

        source_path, chosen, _ref, cfg_dir = _resolve_inputs(
            roots, source, lang, None, config_dir
        )
        lock_path, entries, options = _lock_inputs(roots, source_path, chosen, cfg_dir, lockfile)
        try:
            updated, result = update_locks(
                source_path,
                chosen,
                entries,
                options,
                only=list(target or []),
                force=force,
                reason=reason,
                owner=owner,
            )
        except Exception as exc:  # noqa: BLE001 - surfaced verbatim
            raise ToolError(str(exc)) from exc

        wrote = False
        if result.changed and not dry_run:
            write_locks(lock_path, updated.values())
            wrote = True

        return {
            "ok": result.clean,
            "lockfile": _rel(roots, lock_path),
            "written": wrote,
            "dry_run": dry_run,
            "added": [{"target": e.target, "kind": e.kind, "digest": e.digest} for e in result.added],
            "rebaselined": [
                {"target": e.target, "kind": e.kind, "digest": e.digest} for e in result.updated
            ],
            "released": [e.target for e in result.removed],
            "blocked": [
                {"target": v.target, "file": v.file, "line": v.line, "message": v.message}
                for v in result.blocked
            ],
            "stale": [e.target for e in result.stale],
            "unchanged": result.unchanged,
            "hint": (
                "Locked implementations changed and were left untouched. Re-run with "
                "force=True only if the user has approved accepting these changes."
                if result.blocked and not force
                else ""
            ),
        }

    # ------------------------------------------------------- the review loop

    @mcp.tool()
    def cdec_issues(
        config_dir: Optional[str] = None,
        source: Optional[str] = None,
        reference: Optional[str] = None,
        base_ref: Optional[str] = None,
        repo: Optional[str] = None,
        include_waived: bool = False,
        engine: Optional[Literal["check", "enforce", "lock"]] = None,
    ) -> dict[str, Any]:
        """Every issue all three engines report right now, as one keyed list.

        This is the triage view: one flat list with a stable `key` per issue, so
        you can hand specific keys to `cdec_allow`. Already-accepted issues are
        excluded unless `include_waived=True` (needed to withdraw one). `skipped`
        names engines or rules that could not run — a skipped engine looks
        exactly like a clean one otherwise.
        """
        _cfg_dir, collected = _collect(
            roots,
            config_dir,
            source=source,
            reference=reference,
            base_ref=base_ref,
            repo=repo,
        )
        issues = [
            i
            for i in collected.issues
            if (include_waived or not i.waived) and (engine is None or i.engine == engine)
        ]
        return {
            "ok": not [i for i in issues if not i.waived],
            "baseline": _rel(roots, collected.baseline_path),
            "engines_ran": sorted(collected.engines_ran),
            "skipped": [{"engine": e, "reason": r} for e, r in collected.skipped],
            "issues": [_issue_json(i) for i in issues],
            "summary": {
                "total": len(issues),
                "open": sum(1 for i in issues if not i.waived),
                "waived": sum(1 for i in issues if i.waived),
                "by_engine": {
                    name: sum(1 for i in issues if i.engine == name)
                    for name in ("check", "enforce", "lock")
                },
            },
        }

    @mcp.tool()
    def cdec_allow(
        keys: list[str],
        reason: str = "",
        config_dir: Optional[str] = None,
        source: Optional[str] = None,
        reference: Optional[str] = None,
        base_ref: Optional[str] = None,
        repo: Optional[str] = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Accept issues by key, recording the decision in `.cdec/baseline.yaml`.

        Ask the user before waiving anything — this switches off a rule they
        asked for. Always pass a `reason`; it is what makes the ledger
        reviewable. Keys must name issues the engines report right now, so a
        stale key is an error rather than a silent no-op.

        Lock issues (`L-…`) are refused by design: use `cdec_lock_set(force=True)`.
        """
        from code_constraints.waivers import allow_keys, save_waivers

        _cfg_dir, collected = _collect(
            roots,
            config_dir,
            source=source,
            reference=reference,
            base_ref=base_ref,
            repo=repo,
        )
        result = allow_keys(collected.store, collected, keys, reason=reason)
        if result.changed and not dry_run:
            save_waivers(collected.baseline_path, collected.store)

        payload = _apply_result_json(result)
        payload.update(
            {
                "ok": not result.failed,
                "baseline": _rel(roots, collected.baseline_path),
                "written": result.changed and not dry_run,
                "dry_run": dry_run,
            }
        )
        return payload

    @mcp.tool()
    def cdec_waivers_list(
        config_dir: Optional[str] = None,
        engine: Optional[Literal["check", "enforce"]] = None,
    ) -> dict[str, Any]:
        """Show what is currently accepted in the waiver ledger, and why.

        Needs no source parse, so it works even when the code doesn't parse.
        """
        from code_constraints.waivers import load_waivers
        from code_constraints.waivers.store import WaiverFileError

        cfg_dir = roots.config_dir(config_dir)
        path = cfg_dir / BASELINE_FILENAME
        try:
            store = load_waivers(path)
        except WaiverFileError as exc:
            raise ToolError(str(exc)) from exc

        waivers = [w for w in store.waivers if engine is None or w.engine == engine]
        return {
            "baseline": _rel(roots, path),
            "waivers": [
                {
                    "key": w.key,
                    "engine": w.engine,
                    "rule": w.rule,
                    "qualified_name": w.qualified_name,
                    "detail": w.detail,
                    "reason": w.reason,
                    "added": w.added,
                    "added_by": w.added_by,
                }
                for w in sorted(
                    waivers, key=lambda w: (w.engine, w.rule, w.qualified_name, w.detail)
                )
            ],
            "count": len(waivers),
        }

    @mcp.tool()
    def cdec_waiver_remove(
        keys: list[str],
        config_dir: Optional[str] = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Withdraw waivers by key so those issues block again.

        Needs no source parse — the ledger alone identifies what to drop, so a
        waiver can always be withdrawn even if the code no longer parses.
        """
        from code_constraints.waivers import remove_keys, save_waivers

        cfg_dir = roots.config_dir(config_dir)
        path = cfg_dir / BASELINE_FILENAME
        store = _load_store(path)
        result = remove_keys(store, keys)
        if result.changed and not dry_run:
            save_waivers(path, store)

        payload = _apply_result_json(result)
        payload.update(
            {
                "ok": not (result.malformed or result.not_waived),
                "baseline": _rel(roots, path),
                "written": result.changed and not dry_run,
                "dry_run": dry_run,
            }
        )
        return payload

    @mcp.tool()
    def cdec_waivers_prune(
        config_dir: Optional[str] = None,
        source: Optional[str] = None,
        reference: Optional[str] = None,
        base_ref: Optional[str] = None,
        repo: Optional[str] = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Drop waivers for issues that no longer occur.

        A stale waiver silently pre-approves a future violation of the same rule
        on the same element. Only prunes engines that actually ran this time, so
        a skipped engine never looks like a clean one.
        """
        from code_constraints.waivers import prune as prune_waivers
        from code_constraints.waivers import save_waivers

        _cfg_dir, collected = _collect(
            roots,
            config_dir,
            source=source,
            reference=reference,
            base_ref=base_ref,
            repo=repo,
        )
        stale = prune_waivers(collected.store, collected)
        if stale and not dry_run:
            save_waivers(collected.baseline_path, collected.store)
        return {
            "ok": True,
            "baseline": _rel(roots, collected.baseline_path),
            "written": bool(stale) and not dry_run,
            "dry_run": dry_run,
            "pruned": [
                {
                    "key": w.key,
                    "engine": w.engine,
                    "rule": w.rule,
                    "qualified_name": w.qualified_name,
                    "detail": w.detail,
                }
                for w in stale
            ],
            "engines_ran": sorted(collected.engines_ran),
        }

    # -------------------------------------------------------- model pipeline

    @mcp.tool()
    def cdec_parse(
        out: str,
        source: Optional[str] = None,
        lang: Optional[str] = None,
        config_dir: Optional[str] = None,
    ) -> dict[str, Any]:
        """Parse a source tree into a model file (`.xmi` or `.json`).

        The extension of `out` picks the format: `.json` is the hand- and
        agent-editable editor shape, `.xmi` is the on-disk source of truth.
        """
        source_path, chosen, _ref, _cfg = _resolve_inputs(
            roots, source, lang, None, config_dir
        )
        out_path = roots.path(out)
        assert out_path is not None
        project = _parse(source_path, chosen)
        _save_model(project, out_path)
        return {
            "ok": True,
            "wrote": _rel(roots, out_path),
            "source": _rel(roots, source_path),
            "language": chosen,
            "classes": _count_classes(project),
        }

    @mcp.tool()
    def cdec_convert(src: str, dest: str) -> dict[str, Any]:
        """Convert a model file between XMI 2.1 and editor JSON.

        `cdec_convert("model.xmi", "model.json")` gives you an editable version
        of a parsed architecture; converting back produces standard XMI again.
        """
        src_path = roots.require_file(src, what="source model")
        dest_path = roots.path(dest)
        assert dest_path is not None
        project = _load_model(src_path)
        _save_model(project, dest_path)
        return {
            "ok": True,
            "wrote": _rel(roots, dest_path),
            "classes": _count_classes(project),
        }

    @mcp.tool()
    def cdec_reference_test(
        source: Optional[str] = None,
        lang: Optional[str] = None,
        reference: Optional[str] = None,
        config_dir: Optional[str] = None,
    ) -> dict[str, Any]:
        """Report every structural deviation of the code from the reference model.

        Stricter and more literal than `cdec_check`: added/removed classes,
        added/removed members, changed signatures, return types, access levels,
        modifiers, class kind and base classes. This is the CI gate for "the
        code matches the agreed architecture".
        """
        from code_constraints.reference import compare_to_reference, format_human, to_json

        source_path, chosen, ref_path, _cfg = _resolve_inputs(
            roots, source, lang, reference, config_dir
        )
        if not ref_path.is_file():
            raise ToolError(
                f"reference model not found: {_rel(roots, ref_path)} — create one with "
                "`cdec_reference_update` (snapshot the code) or `cdec_reference_set` "
                "(promote an agreed proposal)."
            )
        reference_proj = _load_model(ref_path)
        current = _parse(source_path, chosen)
        try:
            deviations = compare_to_reference(reference_proj, current)
        except ValueError as exc:
            raise ToolError(str(exc)) from exc

        return {
            "ok": not deviations,
            "source": _rel(roots, source_path),
            "reference": _rel(roots, ref_path),
            "deviations": to_json(deviations),
            "count": len(deviations),
            "text": format_human(deviations),
        }

    @mcp.tool()
    def cdec_reference_set(
        model: str,
        reference: Optional[str] = None,
        config_dir: Optional[str] = None,
    ) -> dict[str, Any]:
        """Promote an authored model file to be the project's target architecture.

        This is the "accept the proposal" step: after the user agrees to a design
        you proposed with `cdec_propose`, this writes it to the reference model so
        `cdec_check` and `cdec_reference_test` start constraining development
        against it. Confirm with the user first — it changes what the whole
        project is gated on.
        """
        model_path = roots.require_file(model, what="model file")
        cfg_dir = roots.config_dir(config_dir)
        ref_path = roots.path(reference)
        if ref_path is None:
            try:
                cfg = load_project_config(cfg_dir)
                ref_path = cfg.reference or (cfg_dir / REFERENCE_FILENAME)
            except ConfigError:
                ref_path = cfg_dir / REFERENCE_FILENAME

        project = _load_model(model_path)
        _save_model(project, ref_path)
        return {
            "ok": True,
            "reference": _rel(roots, ref_path),
            "from": _rel(roots, model_path),
            "classes": _count_classes(project),
        }

    @mcp.tool()
    def cdec_reference_update(
        source: Optional[str] = None,
        lang: Optional[str] = None,
        reference: Optional[str] = None,
        config_dir: Optional[str] = None,
    ) -> dict[str, Any]:
        """Re-snapshot the CURRENT code as the reference architecture.

        This accepts the code as-is and erases the drift the reference was there
        to detect, so confirm with the user before calling it. To adopt a
        *designed* architecture instead, use `cdec_reference_set`.
        """
        source_path, chosen, ref_path, _cfg = _resolve_inputs(
            roots, source, lang, reference, config_dir
        )
        project = _parse(source_path, chosen)
        _save_model(project, ref_path)
        return {
            "ok": True,
            "reference": _rel(roots, ref_path),
            "source": _rel(roots, source_path),
            "language": chosen,
            "classes": _count_classes(project),
        }

    @mcp.tool()
    def cdec_propose(
        model: str,
        source: Optional[str] = None,
        lang: Optional[str] = None,
        config_dir: Optional[str] = None,
        against: Literal["source", "reference", "none"] = "source",
        focus: Optional[list[str]] = None,
        host: str = "127.0.0.1",
        port: int = 8765,
        start_viewer: bool = True,
    ) -> dict[str, Any]:
        """Show a proposed architecture in the browser, diffed against the code.

        The design-review loop: write a model `.json`, propose it, and the user
        sees green for "still to build" and red for "to be removed". Re-proposing
        after an edit refreshes the already-open tab in place — no new tabs — so
        iterate by calling this repeatedly with the same `model`. `focus` pre-
        filters the diagram to the given qualified class names.

        Returns the viewer URL; give it to the user so they can look at it. When
        the design is agreed, lock it with `cdec_reference_set`.
        """
        from code_constraints.core.editor_io import project_to_json

        model_path = roots.require_file(model, what="model file")
        source_path, chosen, ref_path, _cfg = _resolve_inputs(
            roots, source, lang, None, config_dir
        )
        proposal = _load_model(model_path)
        base_url = f"http://{host}:{port}"
        focus_list = [f.strip() for f in (focus or []) if f.strip()]
        focus_q = quote(",".join(focus_list)) if focus_list else ""

        started = False
        if not _server_alive(base_url):
            if not start_viewer:
                raise ToolError(
                    f"no code-constraints viewer is running on {base_url}. Start one with "
                    "`cdec serve`, or call this tool again with start_viewer=True."
                )
            _spawn_viewer(host, port, roots.project_root)
            started = _wait_for_server(base_url, timeout=30.0)
            if not started:
                raise ToolError(
                    f"started a viewer but {base_url} did not come up within 30s. "
                    "Run `cdec serve` manually and retry."
                )

        if against == "reference" and not ref_path.is_file():
            raise ToolError(f"reference model not found: {_rel(roots, ref_path)}")

        try:
            info = _http_json(
                "POST", f"{base_url}/api/projects", {"path": str(source_path), "lang": chosen}
            )
            result = _http_json(
                "POST",
                f"{base_url}/api/projects/{info['id']}/proposal"
                f"?against={against}&focus={focus_q}",
                project_to_json(proposal),
            )
        except RuntimeError as exc:
            raise ToolError(f"pushing the proposal failed: {exc}") from exc

        url = (
            f"{base_url}/?xmi={result['id']}&project={result['project_id']}"
            f"&path={quote(f'proposal: {model_path.name}')}&lang={chosen}&proposal=1"
            + (f"&focus={focus_q}" if focus_q else "")
        )
        return {
            "ok": True,
            "url": url,
            "seq": result["seq"],
            "against": against,
            "focus": focus_list,
            "viewer_started": started,
            "note": (
                "Share this URL with the user. Re-proposing the same model refreshes "
                "an open tab in place. When agreed, call cdec_reference_set."
                if result["seq"] == 1
                else "An open viewer tab refreshed automatically."
            ),
        }

    return mcp


# --------------------------------------------------------------------------
# small stdlib helpers (kept module-level so they're unit-testable)
# --------------------------------------------------------------------------

def _package_version() -> str:
    """The installed distribution version, reported in the MCP handshake."""
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("code-constraints")
    except PackageNotFoundError:  # running from a source tree, not installed
        return "0+unknown"


def _load_store(path: Path) -> "WaiverStore":
    from code_constraints.waivers import load_waivers
    from code_constraints.waivers.store import WaiverFileError

    try:
        return load_waivers(path)
    except WaiverFileError as exc:
        raise ToolError(str(exc)) from exc


def _server_alive(base_url: str) -> bool:
    """True if a code-constraints viewer answers at `base_url`."""
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(f"{base_url}/api/projects", timeout=1.5):
            return True
    except (urllib.error.URLError, OSError, TimeoutError):
        return False


def _wait_for_server(base_url: str, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _server_alive(base_url):
            return True
        time.sleep(0.5)
    return False


def _spawn_viewer(host: str, port: int, cwd: Path) -> None:
    """Start `cdec serve` detached.

    Detached matters twice over: the MCP server owns stdout as the protocol
    channel, so the child must never inherit it, and the viewer has to outlive
    the tool call that started it.
    """
    kwargs: dict[str, Any] = {}
    if sys.platform == "win32":
        # getattr, not attribute access: these constants only exist on Windows,
        # so naming them directly fails type-checking on every other platform.
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(
            subprocess, "DETACHED_PROCESS", 0
        )
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(
        [sys.executable, "-m", "code_constraints.cli", "serve", "--host", host, "--port", str(port)],
        cwd=str(cwd),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **kwargs,
    )


def _http_json(
    method: str, url: str, payload: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Minimal JSON-over-HTTP client (stdlib only). Raises on non-2xx."""
    import urllib.error
    import urllib.request

    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("content-type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{exc.code} {exc.reason}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(str(exc.reason)) from exc
    parsed: dict[str, Any] = json.loads(body or b"null")
    return parsed
