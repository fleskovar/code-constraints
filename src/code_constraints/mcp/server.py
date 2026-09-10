"""The MCP tool surface over code-constraints.

Every tool calls the library in-process rather than shelling out to `cdec`, for
two reasons: results come back as structured JSON instead of human text, and the
issue keys (`V-`/`F-`/`L-`/`R-`) are derived by exactly the same code path the
CLI uses — so a key an agent reads from `cdec_check` is the same key
`cdec exceptions allow` accepts on the command line.

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
from typing import TYPE_CHECKING, Any, Literal, Optional, cast, get_args
from urllib.parse import quote

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from code_constraints.core.rulesdoc import RULES_FILENAME
from code_constraints.lint.config import (
    REFERENCE_FILENAME,
    ConfigError,
    legacy_files,
    load_project_config,
    load_rules,
)

if TYPE_CHECKING:
    # Annotation-only: the engines are imported lazily inside each tool so that
    # building the server (which every harness does at startup) stays cheap.
    from code_constraints.core.model import Project
    from code_constraints.lint.config import LoadedRules, ProjectConfig
    from code_constraints.waivers import ApplyResult, Collected, Issue

Language = Literal[
    "python", "csharp", "typescript", "svelte", "odin", "lua", "julia"
]

SERVER_INSTRUCTIONS = """\
code-constraints (`cdec`) enforces architectural and implementation constraints \
on a codebase. Everything lives in one committed file, `.cdec/rules.yaml`: the \
settings, the rules enforced, the exceptions granted, and the digests of frozen \
implementations.

`cdec_check` is the whole gate. Four kinds of rule run inside it, and each one
carries its own key prefix so you can tell them apart:

  * V- configured architectural rules — drift, dependencies, naming, shape
  * F- `tag-conformance` ............. does the code OBEY its @sealed /
                                       @immutable / @factory / @no_instantiation
                                       tags, checked in the method bodies
  * L- `implementation-locks` ........ did an @locked body CHANGE at all
  * R- `reference-architecture` ...... any structural deviation from
                                       .cdec/reference.xmi

Typical flows:

  Gate a change      -> cdec_check. One call, one verdict.
  Triage everything  -> cdec_issues, one keyed list across every rule.
  Accept a violation -> cdec_allow(keys=["V-1A2B3C4D"], reason="why").
                        Locks are NOT acceptable this way; approve one with
                        cdec_accept(what=["locks"], force=True), which leaves a
                        reviewable diff on the `locks:` section of rules.yaml.
  Adopt on old code  -> cdec_accept(what=["rules"]) grandfathers today's
                        violations so only NEW ones fail.
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
            f"no source given and none found in "
            f"{_rel(roots, cfg_dir / RULES_FILENAME)}; pass `source`, or scaffold "
            f"the project with `cdec init`."
        )
    if not source_path.is_dir():
        raise ToolError(f"source is not a directory: {source_path}")

    chosen = lang or (cfg.language if cfg else None) or detect_language(source_path)
    if chosen is None:
        raise ToolError(
            f"could not determine a language for {_rel(roots, source_path)}; pass `lang`."
        )
    if chosen not in get_args(Language):
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


def _project(roots: _Roots, config_dir: str | None) -> tuple[Path, "ProjectConfig", "LoadedRules"]:
    """(config_dir, settings, rules) — everything read out of `.cdec/rules.yaml`."""
    cfg_dir = roots.config_dir(config_dir)
    try:
        return cfg_dir, load_project_config(cfg_dir), load_rules(cfg_dir)
    except ConfigError as exc:
        raise ToolError(str(exc)) from exc


def _source_context(roots: _Roots, cfg_dir: Path, cfg: "ProjectConfig", source: Path,
                    reference: Path | None) -> Any:
    from code_constraints.lint.engine import SourceContext

    return SourceContext(
        source=source,
        language=cfg.language,
        config_dir=cfg_dir,
        reference_path=reference or cfg.reference_path,
    )


def _collect(
    roots: _Roots, config_dir: str | None, **opts: Any
) -> tuple[Path, "Collected"]:
    """Run every rule and return the keyed `Collected` issue list."""
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
        "rule_id": issue.rule_id,
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

        Start here when you don't know whether a repo uses cdec, which rules are
        active, or where its reference model lives.
        """
        cfg_dir = roots.config_dir(config_dir)
        rules_file = cfg_dir / RULES_FILENAME
        out: dict[str, Any] = {
            "project_root": str(roots.project_root),
            "config_dir": _rel(roots, cfg_dir),
            "rules_file": _rel(roots, rules_file),
            "configured": False,
        }
        try:
            cfg = load_project_config(cfg_dir)
        except ConfigError as exc:
            out["error"] = str(exc)
            out["hint"] = "Run `cdec init` in the project to scaffold `.cdec/rules.yaml`."
            return out

        ref = cfg.reference_path
        rules: list[dict[str, Any]] = []
        rules_error = None
        try:
            for rule in load_rules(cfg_dir).rules:
                rules.append(
                    {"id": rule.rule_id, "type": rule.type_name,
                     "severity": rule.severity.value, "scope": rule.scope}
                )
        except ConfigError as exc:
            rules_error = str(exc)

        n_exceptions = 0
        try:
            from code_constraints.waivers import load_waivers

            n_exceptions = len(load_waivers(cfg_dir).waivers)
        except Exception as exc:  # noqa: BLE001 - reported, not fatal
            out["exceptions_error"] = str(exc)

        n_locks = 0
        try:
            from code_constraints.lock import load_locks

            n_locks = len(load_locks(cfg_dir))
        except Exception as exc:  # noqa: BLE001 - reported, not fatal
            out["locks_error"] = str(exc)

        stale = [_rel(roots, path) for path in legacy_files(cfg_dir)]
        out.update(
            {
                "configured": True,
                "language": cfg.language,
                "source": _rel(roots, cfg.source),
                "reference": {"path": _rel(roots, ref), "exists": ref.is_file()},
                "rules": rules,
                "rules_error": rules_error,
                "exceptions": n_exceptions,
                "locks": n_locks,
            }
        )
        if stale:
            out["legacy_files"] = stale
            out["legacy_hint"] = (
                "These per-concern files are superseded by rules.yaml. They are still "
                "read; fold them in with `cdec init --migrate`."
            )
        return out

    @mcp.tool()
    def cdec_rules() -> dict[str, Any]:
        """List the constraint tags that can be written on code.

        These are the decorators/attributes/macros (`@no_instantiation`,
        `[Sealed]`, `---@cdec layer(...)`, …) that the `tag-conformance`,
        `frozen-rules`, `layer-dependencies` and `implementation-locks` rules
        read. Use this before adding a tag so you use the real name, its legal
        targets, and its parameters.
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

    @mcp.tool()
    def cdec_rule_types() -> dict[str, Any]:
        """List the rule types that can appear in `.cdec/rules.yaml`.

        Use this before writing a rule so you use a `type:` that exists. Each
        entry says which key prefix its violations carry and whether it can
        record a baseline of its own.
        """
        from code_constraints.lint.rules import get_rule_class, known_rule_types

        out = []
        for name in known_rule_types():
            cls = get_rule_class(name)
            assert cls is not None
            out.append(
                {
                    "type": name,
                    "default_scope": cls.default_scope,
                    "reads_source": name in (
                        "tag-conformance", "implementation-locks", "reference-architecture"
                    ),
                    "baselines_itself": cls.supports_auto_accept,
                    "summary": (cls.__doc__ or "").strip().splitlines()[0] if cls.__doc__ else "",
                }
            )
        return {"rule_types": out}

    # ------------------------------------------------------------- the gate

    @mcp.tool()
    def cdec_check(
        config_dir: Optional[str] = None,
        source: Optional[str] = None,
        reference: Optional[str] = None,
        base_ref: Optional[str] = None,
        repo: Optional[str] = None,
        fail_on: Literal["error", "warning", "none"] = "error",
        bypass_locks: bool = False,
        bypass_reason: str = "",
    ) -> dict[str, Any]:
        """Check the project against every rule in `.cdec/rules.yaml`.

        This is the whole gate — configured architectural rules, source-tag
        conformance, implementation locks and the reference-architecture check
        all run here, because they are all rule types in that one file.

        `base_ref` diffs against a git revision instead of the reference model;
        `scope: diff` rules are skipped (and named in `skipped`) when neither
        baseline is available, so a rule that could not run never looks like one
        that passed.

        `ok` is the pass/fail verdict. Every violation carries a `key` that
        `cdec_allow` accepts — except lock violations, which are not acceptable
        that way.
        """
        from code_constraints.lint.baseline import load_baseline
        from code_constraints.lint.engine import run_checks
        from code_constraints.lint.pipeline import PipelineError, resolve_baseline
        from code_constraints.lint.rules.base import Severity

        cfg_dir, cfg, loaded = _project(roots, config_dir)
        source_path = roots.path(source) or cfg.source
        ref_path = roots.path(reference)
        head = _parse(source_path, cfg.language)
        try:
            annotated, has_diff, base_proj = resolve_baseline(
                head_proj=head,
                lang=cfg.language,
                config_dir=cfg_dir,
                explicit_reference=ref_path,
                explicit_base_ref=base_ref,
                repo_path=roots.path(repo) or roots.project_root,
                default_reference=cfg.reference,
            )
        except PipelineError as exc:
            raise ToolError(str(exc)) from exc

        report = run_checks(
            annotated,
            loaded.rules,
            has_diff=has_diff,
            baseline=load_baseline(cfg_dir),
            baseline_project=base_proj,
            source_context=_source_context(roots, cfg_dir, cfg, source_path, ref_path),
            bypass_locks=bypass_locks,
            bypass_reason=bypass_reason,
        )
        payload = report.to_json()
        payload.update(
            {
                "ok": not report.has_failures(Severity(fail_on)),
                "source": _rel(roots, source_path),
                "language": cfg.language,
                "has_baseline": has_diff,
                "rules_file": _rel(roots, cfg_dir / RULES_FILENAME),
                "text": report.to_human(),
            }
        )
        return payload

    @mcp.tool()
    def cdec_accept(
        what: list[Literal["rules", "locks", "reference"]],
        config_dir: Optional[str] = None,
        source: Optional[str] = None,
        reference: Optional[str] = None,
        base_ref: Optional[str] = None,
        repo: Optional[str] = None,
        force: bool = False,
    ) -> dict[str, Any]:
        """Record the code as it stands now as approved, instead of failing on it.

        The counterpart of `cdec check --automatic-exceptions`. Ask the user
        before calling any of these — each one switches off detection the
        project asked for:

          "rules"     grandfather every current violation into `exceptions:`, so
                      only NEW ones fail. The adoption move on an existing
                      codebase.
          "locks"     record digests for newly @locked elements. Safe on its own:
                      without `force` it can only ADD locks, never erase evidence
                      that a frozen body changed. With `force=True` it ACCEPTS a
                      change to frozen code — only ever with explicit approval.
          "reference" re-snapshot .cdec/reference.xmi from the current source,
                      which erases the drift the reference existed to detect.

        Order is fixed: the reference and the locks settle first, then the checks
        re-run, and only what is still reported gets grandfathered — otherwise
        you would write exceptions for issues the re-snapshot was about to erase.
        """
        from code_constraints.core.model import Project
        from code_constraints.lint.baseline import write_baseline
        from code_constraints.lint.engine import run_checks
        from code_constraints.lint.pipeline import PipelineError, resolve_baseline
        from code_constraints.lint.rules.base import RuleContext, RuleSkipped

        accept = set(what)
        if not accept:
            raise ToolError("`what` must name at least one of: rules, locks, reference")
        cfg_dir, cfg, loaded = _project(roots, config_dir)
        source_path = roots.path(source) or cfg.source
        ref_path = roots.path(reference)
        ctx_info = _source_context(roots, cfg_dir, cfg, source_path, ref_path)

        out: dict[str, Any] = {"ok": True, "recorded": {}, "skipped": []}
        auto_ctx = RuleContext(
            # `load_project_config` already validated the language against
            # SUPPORTED_LANGUAGES, so this narrows rather than re-checks.
            project=Project(source_language=cast(Language, cfg.language)),
            has_diff=False,
            source=ctx_info.source,
            language=ctx_info.language,
            config_dir=ctx_info.config_dir,
            reference_path=ctx_info.reference_path,
        )
        for name, type_name in (
            ("reference", "reference-architecture"),
            ("locks", "implementation-locks"),
        ):
            if name not in accept:
                continue
            rules = loaded.of_type(type_name)
            if not rules:
                out["skipped"].append(
                    {"what": name, "reason": f"no `{type_name}` rule in rules.yaml"}
                )
                continue
            lines: list[str] = []
            for rule in rules:
                try:
                    lines.extend(rule.accept_current_state(auto_ctx, force=force))
                except RuleSkipped as exc:
                    out["skipped"].append({"what": name, "reason": str(exc)})
            out["recorded"][name] = lines

        if "rules" in accept:
            head = _parse(source_path, cfg.language)
            try:
                annotated, has_diff, base_proj = resolve_baseline(
                    head_proj=head,
                    lang=cfg.language,
                    config_dir=cfg_dir,
                    explicit_reference=ref_path,
                    explicit_base_ref=base_ref,
                    repo_path=roots.path(repo) or roots.project_root,
                    default_reference=cfg.reference,
                )
            except PipelineError as exc:
                raise ToolError(str(exc)) from exc
            report = run_checks(
                annotated,
                loaded.rules,
                has_diff=has_diff,
                baseline=None,
                baseline_project=base_proj,
                source_context=ctx_info,
            )
            grandfathered = [v for v in report.violations if v.waivable]
            write_baseline(cfg_dir, grandfathered)
            out["recorded"]["rules"] = [
                {"key": v.key(), "rule_id": v.rule_id, "qualified_name": v.qualified_name}
                for v in grandfathered
            ]
            refused = [v for v in report.violations if not v.waivable]
            if refused:
                out["not_grandfathered"] = [
                    {"key": v.key(), "qualified_name": v.qualified_name} for v in refused
                ]
                out["hint"] = (
                    "Lock violations are never grandfathered as exceptions. Accept one "
                    "with cdec_accept(what=['locks'], force=True), and only with the "
                    "user's approval."
                )
        out["rules_file"] = _rel(roots, cfg_dir / RULES_FILENAME)
        return out

    @mcp.tool()
    def cdec_locks(
        source: Optional[str] = None,
        lang: Optional[str] = None,
        config_dir: Optional[str] = None,
    ) -> dict[str, Any]:
        """List which elements are lockable, which are tagged, and which are frozen.

        Use it to see what a `@locked` / `[Locked]` tag would cover before you
        write one, and to spot tags that have never been recorded in the ledger.
        Verifying the locks is `cdec_check`; recording them is
        `cdec_accept(what=["locks"])`.
        """
        from code_constraints.lock import (
            LockOptions,
            UnsupportedLockLanguage,
            collect_targets,
            is_locked_target,
            load_locks,
        )

        source_path, chosen, _ref, cfg_dir = _resolve_inputs(
            roots, source, lang, None, config_dir
        )
        from code_constraints.lint.rules.implementation_locks import ImplementationLocks

        options = LockOptions()
        try:
            loaded = load_rules(cfg_dir)
        except ConfigError:
            loaded = None
        if loaded is not None:
            for rule in loaded.of_type("implementation-locks"):
                # `of_type` matches on the registered name, so this always holds;
                # the isinstance is what tells the type checker so.
                if isinstance(rule, ImplementationLocks):
                    options = rule.lock_options()
                    break
        entries = load_locks(cfg_dir)
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
            "rules_file": _rel(roots, cfg_dir / RULES_FILENAME),
            "rule_configured": bool(loaded and loaded.of_type("implementation-locks")),
            "targets": rows,
            "stale_entries": stale,
            "summary": {
                "lockable": len(rows),
                "tagged": sum(1 for r in rows if r["tagged"]),
                "baselined": sum(1 for r in rows if r["baselined"]),
                "stale": len(stale),
            },
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
        engine: Optional[Literal["check", "enforce", "lock", "reference"]] = None,
        rule_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Every issue `cdec check` reports right now, as one keyed list.

        The triage view: one flat list with a stable `key` per issue, so you can
        hand specific keys to `cdec_allow`. Filter by `engine` (the key prefix's
        family) or by `rule_id` (the `rules.yaml` entry). Already-accepted issues
        are excluded unless `include_waived=True` (needed to withdraw one).
        `skipped` names rules that could not run — a skipped rule looks exactly
        like a clean one otherwise.
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
            if (include_waived or not i.waived)
            and (engine is None or i.engine == engine)
            and (rule_id is None or i.rule_id == rule_id)
        ]
        return {
            "ok": not [i for i in issues if not i.waived],
            "rules_file": _rel(roots, collected.ledger_path),
            "rules_ran": sorted(collected.rules_ran),
            "engines_ran": sorted(collected.engines_ran),
            "skipped": [{"rule_id": r, "reason": why} for r, why in collected.skipped],
            "issues": [_issue_json(i) for i in issues],
            "summary": {
                "total": len(issues),
                "open": sum(1 for i in issues if not i.waived),
                "waived": sum(1 for i in issues if i.waived),
                "by_engine": {
                    name: sum(1 for i in issues if i.engine == name)
                    for name in ("check", "enforce", "lock", "reference")
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
        """Accept issues by key, recording it in the `exceptions:` section of
        `.cdec/rules.yaml`.

        Ask the user before accepting anything — this switches off a rule they
        asked for. Always pass a `reason`; it is what makes the entry reviewable.
        Keys must name issues reported right now, so a stale key is an error
        rather than a silent no-op.

        Lock issues (`L-…`) are refused by design: use
        `cdec_accept(what=["locks"], force=True)`.
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
            save_waivers(_cfg_dir, collected.store)

        payload = _apply_result_json(result)
        payload.update(
            {
                "ok": not result.failed,
                "rules_file": _rel(roots, collected.ledger_path),
                "written": result.changed and not dry_run,
                "dry_run": dry_run,
            }
        )
        return payload

    @mcp.tool()
    def cdec_exceptions_list(
        config_dir: Optional[str] = None,
        engine: Optional[Literal["check", "enforce", "reference"]] = None,
    ) -> dict[str, Any]:
        """Show what is currently accepted as an exception, and why.

        Needs no source parse, so it works even when the code doesn't parse.
        """
        from code_constraints.waivers import load_waivers
        from code_constraints.waivers.store import WaiverFileError

        cfg_dir = roots.config_dir(config_dir)
        try:
            store = load_waivers(cfg_dir)
        except WaiverFileError as exc:
            raise ToolError(str(exc)) from exc

        waivers = [w for w in store.waivers if engine is None or w.engine == engine]
        return {
            "rules_file": _rel(roots, cfg_dir / RULES_FILENAME),
            "exceptions": [
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
    def cdec_exception_remove(
        keys: list[str],
        config_dir: Optional[str] = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Withdraw exceptions by key so those issues block again.

        Needs no source parse — the ledger alone identifies what to drop, so an
        exception can always be withdrawn even if the code no longer parses.
        """
        from code_constraints.waivers import remove_keys, save_waivers

        cfg_dir = roots.config_dir(config_dir)
        store = _load_store(cfg_dir)
        result = remove_keys(store, keys)
        if result.changed and not dry_run:
            save_waivers(cfg_dir, store)

        payload = _apply_result_json(result)
        payload.update(
            {
                "ok": not (result.malformed or result.not_waived),
                "rules_file": _rel(roots, cfg_dir / RULES_FILENAME),
                "written": result.changed and not dry_run,
                "dry_run": dry_run,
            }
        )
        return payload

    @mcp.tool()
    def cdec_exceptions_prune(
        config_dir: Optional[str] = None,
        source: Optional[str] = None,
        reference: Optional[str] = None,
        base_ref: Optional[str] = None,
        repo: Optional[str] = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Drop exceptions for issues that no longer occur.

        A stale exception silently pre-approves a future violation of the same
        rule on the same element. Only prunes engines whose rules actually ran
        this time, so a skipped rule never looks like a clean one.
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
            save_waivers(_cfg_dir, collected.store)
        return {
            "ok": True,
            "rules_file": _rel(roots, collected.ledger_path),
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
    def cdec_reference_set(
        model: str,
        reference: Optional[str] = None,
        config_dir: Optional[str] = None,
    ) -> dict[str, Any]:
        """Promote an authored model file to be the project's target architecture.

        This is the "accept the proposal" step: after the user agrees to a design
        you proposed with `cdec_propose`, this writes it to the reference model,
        so `cdec_check` starts constraining development against it. Confirm with
        the user first — it changes what the whole project is gated on.

        This declares what the code *should become*. To record what it *is*
        instead, use `cdec_accept(what=["reference"])`.
        """
        model_path = roots.require_file(model, what="model file")
        cfg_dir = roots.config_dir(config_dir)
        ref_path = roots.path(reference)
        if ref_path is None:
            try:
                ref_path = load_project_config(cfg_dir).reference_path
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


def _load_store(config_dir: Path) -> Any:
    from code_constraints.waivers import load_waivers
    from code_constraints.waivers.store import WaiverFileError

    try:
        return load_waivers(config_dir)
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
