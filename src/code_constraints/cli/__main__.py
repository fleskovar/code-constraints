"""`cdec` command-line entry point."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Optional
from urllib.parse import quote

import typer
from git import Repo

from code_constraints.cli.detect import detect_language

from code_constraints.core.diff import diff_projects
from code_constraints.core.dot import (
    emit_activity_diagram,
    emit_class_diagram,
    emit_package_diagram,
    emit_sequence_diagram,
)
from code_constraints.core.model_io import UnsupportedModelFormat, load_model, save_model
from code_constraints.core.render import GraphvizNotFound, render_svg
from code_constraints.core.xmi_writer import write_project
from code_constraints.lint.baseline import load_baseline, write_baseline
from code_constraints.lint.config import (
    BASELINE_FILENAME,
    REFERENCE_FILENAME,
    ConfigError,
    load_project_config,
    load_rules,
)
from code_constraints.lint.engine import run_checks
from code_constraints.lint.rules.base import Severity

if TYPE_CHECKING:
    # Annotation-only: the waiver machinery is imported lazily inside the
    # commands that use it, so `cdec parse` doesn't pay for it.
    from code_constraints.enforce.model import Finding
    from code_constraints.waivers import ApplyResult, Collected, Issue, WaiverStore

app = typer.Typer(
    help=(
        "code-constraints (cdec) — enforce architectural and implementation "
        "constraints on a codebase. Model it (parse/render/diff), then gate it: "
        "`check` for architectural drift, `enforce` for implementation "
        "conformance, `lock` for implementation freeze."
    )
)


@app.callback(invoke_without_command=True)
def _default(ctx: typer.Context) -> None:
    """Launch the interactive session when `cdec` is run with no subcommand."""
    if ctx.invoked_subcommand is not None:
        return
    from code_constraints.cli.interactive import run_interactive

    run_interactive(Path.cwd())
    raise typer.Exit()


@app.command()
def parse(
    path: Path = typer.Argument(..., exists=True, file_okay=False, dir_okay=True),
    lang: str = typer.Option(..., "--lang", help="python | csharp | typescript | svelte | odin | lua | julia"),
    out: Path = typer.Option(..., "--out", help="Destination model file (.xmi or .json)"),
) -> None:
    """Parse a source tree and write a model file (XMI 2.1 or editor JSON)."""
    project = _parse_project(path, lang)
    _save_model_cli(project, out)
    typer.echo(f"wrote {out}")


@app.command()
def convert(
    src: Path = typer.Argument(..., exists=True, dir_okay=False, help="Model file to read (.xmi or .json)"),
    dest: Path = typer.Argument(..., help="Destination model file (.xmi or .json)"),
) -> None:
    """Convert a model file between XMI 2.1 and editor JSON.

    The JSON shape is the same one the web editor and the proposal endpoint
    use, so `cdec convert model.xmi model.json` gives you a hand-editable /
    agent-editable version of any parsed architecture — and converting back
    produces standard XMI again.
    """
    project = _load_model_cli(src)
    _save_model_cli(project, dest)
    typer.echo(f"wrote {dest}")


@app.command()
def render(
    xmi: Path = typer.Argument(..., exists=True, dir_okay=False),
    diagram: str = typer.Option(
        ..., "--diagram", help="class | package | activity | sequence"
    ),
    name: Optional[str] = typer.Option(
        None, "--name", help="Required for activity/sequence diagrams."
    ),
    out: Path = typer.Option(..., "-o", "--out", help="Output SVG path"),
) -> None:
    """Render an SVG from a stored model file (.xmi or .json)."""
    project = _load_model_cli(xmi)
    text = _emit(project, diagram, name)
    if text is None:
        typer.echo(f"no diagram of kind {diagram} (name={name}) found", err=True)
        raise typer.Exit(code=1)
    try:
        svg = render_svg(text, cache_dir=Path(".cdec_cache"))
    except GraphvizNotFound as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    out.write_bytes(svg)
    typer.echo(f"wrote {out}")


@app.command()
def diff(
    old_ref: str = typer.Argument(...),
    new_ref: str = typer.Argument(...),
    lang: str = typer.Option(..., "--lang"),
    out: Path = typer.Option(..., "--out"),
    repo: Path = typer.Option(Path("."), "--repo"),
    subpath: str = typer.Option(
        "", "--subpath", help="If set, only parse this directory of each revision."
    ),
) -> None:
    """Diff two git revisions and emit an annotated XMI."""
    repo_path = repo.resolve()
    git_repo = Repo(str(repo_path))
    with tempfile.TemporaryDirectory(prefix="cdec-diff-") as tmp:
        old_dir = _checkout_revision(git_repo, old_ref, Path(tmp) / "old")
        new_dir = _checkout_revision(git_repo, new_ref, Path(tmp) / "new")
        target_old = old_dir / subpath if subpath else old_dir
        target_new = new_dir / subpath if subpath else new_dir
        old_proj = _parse_project(target_old, lang)
        new_proj = _parse_project(target_new, lang)
        annotated = diff_projects(old_proj, new_proj)
        _save_model_cli(annotated, out)
    typer.echo(f"wrote {out}")


@app.command("diff-vs-xmi")
def diff_vs_xmi(
    reference_xmi: Path = typer.Argument(
        ..., exists=True, dir_okay=False,
        help="Reference XMI (the OLDER side of the diff).",
    ),
    source_path: Path = typer.Argument(
        ..., exists=True, file_okay=False, dir_okay=True,
        help="Source tree to parse (the NEWER side of the diff).",
    ),
    lang: str = typer.Option(..., "--lang", help="python | csharp | typescript | svelte | odin | lua | julia"),
    out: Path = typer.Option(..., "--out", help="Destination annotated .xmi"),
) -> None:
    """Parse a source tree and diff it against a reference XMI snapshot.

    Useful when you've checkpointed an earlier version of the model as an XMI
    file and want to see what the current source code looks like relative to
    it. The reference XMI is treated as the OLD side; the freshly-parsed
    source is the NEW. Both must share the same `source_language`.
    """
    old_proj = _load_model_cli(reference_xmi)
    new_proj = _parse_project(source_path, lang)
    try:
        annotated = diff_projects(old_proj, new_proj)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _save_model_cli(annotated, out)
    typer.echo(f"wrote {out}")


@app.command("diff-xmi")
def diff_xmi(
    old_xmi: Path = typer.Argument(..., exists=True, dir_okay=False, help="Older XMI"),
    new_xmi: Path = typer.Argument(..., exists=True, dir_okay=False, help="Newer XMI"),
    out: Path = typer.Option(..., "--out", help="Destination annotated .xmi"),
) -> None:
    """Diff two existing XMI files and emit an annotated XMI.

    Useful when you've already parsed two snapshots independently (e.g. CI
    artefacts from different branches) and just want the diff without re-
    parsing source. Both XMIs must declare the same `source_language`.
    """
    old_proj = _load_model_cli(old_xmi)
    new_proj = _load_model_cli(new_xmi)
    try:
        annotated = diff_projects(old_proj, new_proj)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _save_model_cli(annotated, out)
    typer.echo(f"wrote {out}")


@app.command()
def init(
    config_dir: Path = typer.Option(
        Path(".cdec"), "--config", help="Directory to create (default: .cdec at cwd)."
    ),
    lang: str = typer.Option("python", "--lang", help="python | csharp | typescript | svelte | odin | lua | julia"),
    source: Path = typer.Option(
        Path("."), "--source", help="Source tree parsed by `cdec check`."
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite existing files."),
) -> None:
    """Scaffold a `.cdec/` folder with config, rule templates, and a reference XMI."""
    from code_constraints.cli.scaffold import SUPPORTED_LANGS, ScaffoldError, init_cdec_config

    if lang not in SUPPORTED_LANGS:
        raise typer.BadParameter(f"unsupported language: {lang}")
    if not source.exists():
        typer.echo(f"source {source} does not exist; skipping reference snapshot.", err=True)
    try:
        written = init_cdec_config(config_dir, lang, source, force=force)
    except ScaffoldError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    for path in written:
        typer.echo(f"wrote {path}")


@app.command(name="update-assets")
def update_assets(
    project_root: Path = typer.Option(
        Path("."), "--project-root", help="Project root (default: current directory)."
    ),
    no_agents: bool = typer.Option(False, "--no-agents", help="Skip updating Claude agent files."),
    no_shims: bool = typer.Option(False, "--no-shims", help="Skip updating language shims."),
    lang: Optional[str] = typer.Option(
        None, "--lang", help="Language for shims (auto-detected from .cdec/config.yaml if omitted)."
    ),
) -> None:
    """Update code-constraints assets (Claude agents, shims) to the version bundled with
    this installation. Run after upgrading code-constraints to pick up new agents or shim
    changes in existing projects."""
    from code_constraints.cli.scaffold import ScaffoldError, copy_agents, copy_shims, has_shim

    updated_any = False

    if not no_agents:
        try:
            dests = copy_agents(project_root, force=True)
            for dest in dests:
                typer.echo(f"updated {dest}")
            updated_any = True
        except ScaffoldError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc

    if not no_shims:
        resolved_lang = lang
        if resolved_lang is None:
            config_file = project_root / ".cdec" / "config.yaml"
            if config_file.is_file():
                import yaml  # type: ignore[import-untyped]
                with config_file.open(encoding="utf-8") as f:
                    cfg = yaml.safe_load(f)
                resolved_lang = (cfg or {}).get("language")
        if resolved_lang and has_shim(resolved_lang):
            try:
                dests = copy_shims(project_root, resolved_lang, force=True)
                for dest in dests:
                    typer.echo(f"updated {dest}")
                updated_any = True
            except ScaffoldError as exc:
                typer.echo(str(exc), err=True)
                raise typer.Exit(code=1) from exc

    if not updated_any:
        typer.echo("nothing to update (use --lang to specify a language for shims)")


@app.command()
def update(
    branch: Optional[str] = typer.Option(
        None, "--branch", help="Branch to update to (default: the currently checked-out branch)."
    ),
    no_frontend: bool = typer.Option(
        False, "--no-frontend", help="Skip rebuilding the web UI (faster; leaves dist stale)."
    ),
    force: bool = typer.Option(
        False, "--force", help="Reinstall everything even if dependencies are unchanged."
    ),
) -> None:
    """Update this installation in place — equivalent to re-running the installer.

    Pulls the latest code from GitHub, re-syncs Python dependencies (picking up
    any requirement changes), and rebuilds the web frontend. The refreshed code
    takes effect on the next `cdec` invocation.

    Install steps whose inputs are unchanged since the last run are skipped; use
    --force to reinstall regardless.
    """
    from code_constraints.cli.update import UpdateError, run_update

    try:
        repo_root = run_update(
            branch=branch, frontend=not no_frontend, force=force, echo=typer.echo
        )
    except UpdateError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"\ncode-constraints updated at {repo_root}")


@app.command()
def check(
    config_dir: Path = typer.Option(
        Path(".cdec"), "--config", help="`.cdec/` folder containing config + rules."
    ),
    reference: Optional[Path] = typer.Option(
        None, "--reference", help="Override baseline reference XMI."
    ),
    base_ref: Optional[str] = typer.Option(
        None, "--base-ref", help="Git ref to use as baseline (parsed live)."
    ),
    source: Optional[Path] = typer.Option(
        None, "--source", help="Override source tree from config."
    ),
    update_reference: bool = typer.Option(
        False, "--update-reference", help="Re-snapshot reference.xmi from source and exit."
    ),
    update_baseline_flag: bool = typer.Option(
        False, "--update-baseline", help="Record current violations into baseline.yaml and exit."
    ),
    format: str = typer.Option("human", "--format", help="human | json"),
    json_out: Optional[Path] = typer.Option(None, "--json-out", help="Also write a JSON report."),
    log_out: Optional[Path] = typer.Option(None, "--log-out", help="Also tee human stdout to a log file."),
    fail_on: str = typer.Option("error", "--fail-on", help="error | warning | none"),
    repo: Path = typer.Option(Path("."), "--repo", help="Git repo root (only used with --base-ref)."),
    enforce_flag: bool = typer.Option(
        False, "--enforce",
        help="Also run the decoupled `cdec enforce` conformance engine (Engine B).",
    ),
    no_locks: bool = typer.Option(
        False, "--no-locks",
        help="Skip implementation-lock verification (Engine C), which otherwise runs "
             "whenever `.cdec/locks.yaml` has entries.",
    ),
    bypass_locks: bool = typer.Option(
        False, "--bypass-locks",
        help="Run lock verification but do not fail on it. Prints an audit banner — "
             "intended for a lead unblocking a release, not routine use.",
    ),
    bypass_reason: str = typer.Option(
        "", "--bypass-reason", help="Why locks are being bypassed (recorded in output)."
    ),
) -> None:
    """Run architectural-lint rules against the project."""
    if format not in ("human", "json"):
        raise typer.BadParameter(f"unknown format: {format}")
    try:
        fail_on_sev = Severity(fail_on)
    except ValueError as exc:
        raise typer.BadParameter(f"--fail-on must be error|warning|none, got {fail_on!r}") from exc

    try:
        cfg = load_project_config(config_dir)
    except ConfigError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    source_path = source.resolve() if source else cfg.source

    if update_reference:
        proj = _parse_project(source_path, cfg.language)
        ref_path = reference or (config_dir / REFERENCE_FILENAME)
        _save_model_cli(proj, ref_path)
        typer.echo(f"wrote {ref_path}")
        return

    # Load rules.
    try:
        loaded = load_rules(config_dir)
    except ConfigError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    head_proj = _parse_project(source_path, cfg.language)

    # Resolve baseline source: --base-ref wins, then --reference, then config default.
    annotated, has_diff, base_proj = _resolve_baseline_and_diff(
        head_proj=head_proj,
        cfg_language=cfg.language,
        config_dir=config_dir,
        explicit_reference=reference,
        explicit_base_ref=base_ref,
        repo_path=repo,
        default_reference=cfg.reference,
    )

    baseline_path = config_dir / BASELINE_FILENAME
    baseline = load_baseline(baseline_path)

    if update_baseline_flag:
        report = run_checks(
            annotated, loaded.rules, has_diff=has_diff, baseline=None,
            baseline_project=base_proj,
        )
        write_baseline(baseline_path, report.violations)
        note = f"wrote {baseline_path} with {len(report.violations)} violation(s)"
        if enforce_flag:
            # `--enforce` widened what this run checks, so it widens what
            # "accept the current state" means too.
            note += f" and {_record_findings(baseline_path, source_path, cfg.language)} finding(s)"
        typer.echo(note)
        return

    report = run_checks(
        annotated, loaded.rules, has_diff=has_diff, baseline=baseline,
        baseline_project=base_proj,
    )

    # Emit output. `transcript` accumulates every engine's human text so
    # `--log-out` produces one complete file — which is exactly the file
    # `cdec baseline patch` expects to be handed back, marked up.
    human_text = report.to_human()
    transcript: list[str] = [human_text]
    if format == "human":
        typer.echo(human_text, nl=False)
    else:
        import json as _json
        typer.echo(_json.dumps(report.to_json(), indent=2, sort_keys=True))

    json_target = json_out or cfg.json_out
    if json_target is not None:
        report.write_json(json_target)
        typer.echo(f"wrote {json_target}")

    enforce_failed = False
    if enforce_flag:
        from code_constraints.enforce import enforce as run_enforce
        from code_constraints.enforce import format_findings

        findings = run_enforce(source_path, cfg.language)
        findings, silenced = _filter_findings(findings, baseline.store)
        enforce_text = format_findings(findings, suppressed=len(silenced))
        transcript.append(enforce_text)
        typer.echo(enforce_text, nl=False)
        enforce_failed = bool(findings)

    # Engine C — implementation locks, so a frozen implementation is enforced by
    # the command teams already run in CI rather than needing an extra step. A
    # project with nothing locked prints nothing; a `@locked` tag that was never
    # baselined must still be reported, so the check runs before we know whether
    # the project opted in.
    lock_failed = False
    if not no_locks and cfg.lock.enabled:
        from code_constraints.lock import UnsupportedLockLanguage
        from code_constraints.lock import check_locks as _check_locks
        from code_constraints.lock import format_report as _format_lock_report

        lock_ctx = _lock_context(source_path, cfg.language, config_dir, None)
        opted_in = bool(lock_ctx.entries or lock_ctx.options.patterns)
        try:
            lock_report = _check_locks(
                lock_ctx.source, lock_ctx.lang, lock_ctx.entries, lock_ctx.options,
                bypass=bypass_locks, bypass_reason=bypass_reason,
            )
        except UnsupportedLockLanguage as exc:
            # Only an error for a project that actually asked for locks.
            if opted_in:
                typer.echo(str(exc), err=True)
                raise typer.Exit(code=2) from exc
            lock_report = None
        if lock_report is not None and (
            lock_report.checked or lock_report.declared or lock_report.violations
        ):
            lock_text = _format_lock_report(lock_report)
            transcript.append(lock_text)
            typer.echo(lock_text, nl=False)
            lock_failed = not lock_report.ok

    log_target = log_out or cfg.log_out
    if log_target is not None:
        log_target.parent.mkdir(parents=True, exist_ok=True)
        log_target.write_text("".join(transcript), encoding="utf-8")
        typer.echo(f"wrote {log_target}")

    if report.has_failures(fail_on_sev) or enforce_failed or lock_failed:
        raise typer.Exit(code=1)


@app.command()
def enforce(
    path: Path = typer.Argument(..., exists=True, file_okay=False, dir_okay=True),
    lang: str = typer.Option(..., "--lang", help="python | csharp | typescript | svelte | odin | lua | julia"),
    format: str = typer.Option("human", "--format", help="human | json"),
    json_out: Optional[Path] = typer.Option(None, "--json-out", help="Also write a JSON report."),
    config_dir: Path = typer.Option(
        Path(".cdec"), "--config",
        help="`.cdec/` folder whose baseline.yaml silences accepted findings.",
    ),
    no_baseline: bool = typer.Option(
        False, "--no-baseline", help="Report every finding, including waived ones."
    ),
) -> None:
    """Check implementation conformance to architectural-rule tags (Engine B).

    Independent of `cdec check`: this re-parses the source and inspects method
    bodies (`no-instantiation`, `factory`, `immutable`) plus the structural
    `sealed` rule. It never consults the reference model or the diff.

    Findings accepted through `cdec baseline allow` / `patch` are silenced, so
    a team can adopt a tag without fixing every pre-existing case first.
    """
    if format not in ("human", "json"):
        raise typer.BadParameter(f"unknown format: {format}")
    if lang not in (
        "python", "csharp", "typescript", "svelte", "odin", "lua", "julia",
    ):
        raise typer.BadParameter(f"unsupported language: {lang}")

    from code_constraints.enforce import enforce as run_enforce
    from code_constraints.enforce import findings_to_json, format_findings

    findings = run_enforce(path, lang)
    silenced: list = []
    if not no_baseline:
        from code_constraints.waivers import load_waivers

        findings, silenced = _filter_findings(
            findings, load_waivers(config_dir / BASELINE_FILENAME)
        )

    if format == "human":
        typer.echo(format_findings(findings, suppressed=len(silenced)), nl=False)
    else:
        import json as _json
        typer.echo(_json.dumps(findings_to_json(findings), indent=2, sort_keys=True))

    if json_out is not None:
        import json as _json
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(
            _json.dumps(findings_to_json(findings), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        typer.echo(f"wrote {json_out}")

    if findings:
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# `cdec baseline` — the review loop.
#
# Enforcement that can only say "no" gets switched off. These commands are the
# other half: read the report, decide which issues are acceptable, record the
# decision (with a reason) in `.cdec/baseline.yaml`, and keep moving. Every
# issue prints a stable key, so a decision can be quoted by a human editing a
# text file or by an agent passing a key on the command line — the two paths
# resolve to exactly the same operation.
# ---------------------------------------------------------------------------

baseline_app = typer.Typer(
    help=(
        "Review and accept known violations. `review` writes an editable report, "
        "`patch` applies the lines you marked [ALLOW], `allow`/`remove` take keys "
        "directly."
    )
)
app.add_typer(baseline_app, name="baseline")


@baseline_app.command("review")
def baseline_review(
    config_dir: Path = typer.Option(Path(".cdec"), "--config", help="`.cdec/` folder."),
    out: Optional[Path] = typer.Option(
        None, "--out", "-o", help="Write the review file here (default: stdout)."
    ),
    source: Optional[Path] = typer.Option(None, "--source", help="Override source tree."),
    reference: Optional[Path] = typer.Option(None, "--reference", help="Override baseline reference XMI."),
    base_ref: Optional[str] = typer.Option(None, "--base-ref", help="Git ref to use as baseline."),
    repo: Path = typer.Option(Path("."), "--repo", help="Git repo root (only used with --base-ref)."),
    include_waived: bool = typer.Option(
        False, "--all", help="Include already-accepted issues (mark them [REMOVE] to withdraw)."
    ),
    format: str = typer.Option("text", "--format", help="text | json"),
) -> None:
    """Write every current issue as one markable line per issue.

    Mark the ones you accept with `[ALLOW]` (optionally `[ALLOW: reason]`) and
    feed the file back through `cdec baseline patch`.
    """
    if format not in ("text", "json"):
        raise typer.BadParameter(f"unknown format: {format}")
    collected = _collect_issues_cli(
        config_dir, source=source, reference=reference, base_ref=base_ref, repo=repo
    )
    if format == "json":
        import json as _json

        payload = _json.dumps(
            {
                "issues": [_issue_to_json(i) for i in collected.issues
                           if include_waived or not i.waived],
                "skipped": [{"engine": e, "reason": r} for e, r in collected.skipped],
            },
            indent=2,
            sort_keys=True,
        )
        _write_or_echo(payload + "\n", out)
        return

    from code_constraints.waivers import render_review

    text = render_review(collected.issues, include_waived=include_waived)
    for engine, reason in collected.skipped:
        text += f"# skipped: {engine}: {reason}\n"
    _write_or_echo(text, out)


@baseline_app.command("patch")
def baseline_patch(
    file: Path = typer.Option(
        ..., "--file", "-f",
        help="Reviewed report. Use '-' to read from stdin.",
    ),
    config_dir: Path = typer.Option(Path(".cdec"), "--config", help="`.cdec/` folder."),
    reason: str = typer.Option(
        "", "--reason", help="Reason applied to lines that don't carry [ALLOW: …]."
    ),
    source: Optional[Path] = typer.Option(None, "--source", help="Override source tree."),
    reference: Optional[Path] = typer.Option(None, "--reference", help="Override baseline reference XMI."),
    base_ref: Optional[str] = typer.Option(None, "--base-ref", help="Git ref to use as baseline."),
    repo: Path = typer.Option(Path("."), "--repo", help="Git repo root (only used with --base-ref)."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Report what would change; write nothing."),
    ignore_unknown: bool = typer.Option(
        False, "--ignore-unknown",
        help="Don't fail on keys that match no current issue (e.g. a stale report).",
    ),
) -> None:
    """Apply the `[ALLOW]` / `[REMOVE]` marks in a reviewed report.

    Any text file works — the output of `cdec baseline review`, of
    `cdec check --log-out`, or a hand-written list — because the parser only
    looks for a marker and an issue key on the same line.
    """
    text = _read_review_text(file)

    from code_constraints.waivers import apply_decisions, parse_review, save_waivers

    decisions = parse_review(text)
    if decisions.empty and not decisions.problems:
        typer.echo(
            "no [ALLOW] or [REMOVE] marks found — nothing to apply.\n"
            "Mark a line by adding [ALLOW] anywhere on it."
        )
        return

    collected = _collect_issues_cli(
        config_dir, source=source, reference=reference, base_ref=base_ref, repo=repo
    )
    result = apply_decisions(
        collected.store, collected, decisions, default_reason=reason
    )
    _report_apply(result, collected.baseline_path, dry_run=dry_run)
    if result.changed and not dry_run:
        save_waivers(collected.baseline_path, collected.store)
    _exit_on_apply_failure(result, ignore_unknown=ignore_unknown)


@baseline_app.command("allow")
def baseline_allow(
    keys: list[str] = typer.Argument(..., help="Issue keys, e.g. V-1A2B3C4D."),
    config_dir: Path = typer.Option(Path(".cdec"), "--config", help="`.cdec/` folder."),
    reason: str = typer.Option("", "--reason", help="Why this issue is acceptable."),
    source: Optional[Path] = typer.Option(None, "--source", help="Override source tree."),
    reference: Optional[Path] = typer.Option(None, "--reference", help="Override baseline reference XMI."),
    base_ref: Optional[str] = typer.Option(None, "--base-ref", help="Git ref to use as baseline."),
    repo: Path = typer.Option(Path("."), "--repo", help="Git repo root (only used with --base-ref)."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Report what would change; write nothing."),
) -> None:
    """Accept issues by key — the path an agent or a one-liner takes.

    The keys must name issues the engines report right now; a key that matches
    nothing is an error, not a silent no-op, because it almost always means the
    report being quoted is stale.
    """
    from code_constraints.waivers import allow_keys, save_waivers

    collected = _collect_issues_cli(
        config_dir, source=source, reference=reference, base_ref=base_ref, repo=repo
    )
    result = allow_keys(collected.store, collected, keys, reason=reason)
    _report_apply(result, collected.baseline_path, dry_run=dry_run)
    if result.changed and not dry_run:
        save_waivers(collected.baseline_path, collected.store)
    _exit_on_apply_failure(result)


@baseline_app.command("remove")
def baseline_remove(
    keys: list[str] = typer.Argument(..., help="Issue keys to stop allowing."),
    config_dir: Path = typer.Option(Path(".cdec"), "--config", help="`.cdec/` folder."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Report what would change; write nothing."),
) -> None:
    """Withdraw waivers by key, so the issue blocks again.

    Needs no source parse: the ledger alone identifies what to drop, which
    means a waiver can always be withdrawn even if the code no longer parses.
    """
    from code_constraints.waivers import remove_keys, save_waivers

    baseline_path = config_dir / BASELINE_FILENAME
    store = _load_waivers_cli(baseline_path)
    result = remove_keys(store, keys)
    _report_apply(result, baseline_path, dry_run=dry_run)
    if result.changed and not dry_run:
        save_waivers(baseline_path, store)
    if result.malformed or result.not_waived:
        raise typer.Exit(code=1)


@baseline_app.command("list")
def baseline_list(
    config_dir: Path = typer.Option(Path(".cdec"), "--config", help="`.cdec/` folder."),
    engine: Optional[str] = typer.Option(
        None, "--engine", help="Only show one engine's waivers: check | enforce."
    ),
    format: str = typer.Option("human", "--format", help="human | json"),
) -> None:
    """Show what is currently accepted, and why."""
    if format not in ("human", "json"):
        raise typer.BadParameter(f"unknown format: {format}")
    baseline_path = config_dir / BASELINE_FILENAME
    store = _load_waivers_cli(baseline_path)
    waivers = [w for w in store.waivers if engine is None or w.engine == engine]

    if format == "json":
        import json as _json

        typer.echo(
            _json.dumps(
                [
                    {
                        "key": w.key,
                        "engine": w.engine,
                        "rule": w.rule,
                        "qualifiedName": w.qualified_name,
                        "detail": w.detail,
                        "reason": w.reason,
                        "added": w.added,
                        "addedBy": w.added_by,
                    }
                    for w in waivers
                ],
                indent=2,
                sort_keys=True,
            )
        )
        return

    if not waivers:
        typer.echo(f"no waivers recorded in {baseline_path}.")
        return
    typer.echo(f"{len(waivers)} waiver(s) in {baseline_path}:")
    for w in sorted(waivers, key=lambda w: (w.engine, w.rule, w.qualified_name, w.detail)):
        detail = f" {w.detail}" if w.detail else ""
        typer.echo(f"  - [{w.key}] [{w.engine}/{w.rule}] {w.qualified_name}{detail}")
        meta = ", ".join(
            part for part in (
                f"reason: {w.reason}" if w.reason else "",
                f"added: {w.added}" if w.added else "",
                f"by: {w.added_by}" if w.added_by else "",
            ) if part
        )
        if meta:
            typer.echo(f"      {meta}")


@baseline_app.command("prune")
def baseline_prune(
    config_dir: Path = typer.Option(Path(".cdec"), "--config", help="`.cdec/` folder."),
    source: Optional[Path] = typer.Option(None, "--source", help="Override source tree."),
    reference: Optional[Path] = typer.Option(None, "--reference", help="Override baseline reference XMI."),
    base_ref: Optional[str] = typer.Option(None, "--base-ref", help="Git ref to use as baseline."),
    repo: Path = typer.Option(Path("."), "--repo", help="Git repo root (only used with --base-ref)."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Report what would change; write nothing."),
) -> None:
    """Drop waivers for issues that no longer occur.

    Waivers outlive the code they were granted for, and a stale one silently
    pre-approves a future violation of the same rule on the same element. This
    only prunes engines that actually ran, so a skipped engine never looks like
    a clean one.
    """
    from code_constraints.waivers import prune as prune_waivers
    from code_constraints.waivers import save_waivers

    collected = _collect_issues_cli(
        config_dir, source=source, reference=reference, base_ref=base_ref, repo=repo
    )
    stale = prune_waivers(collected.store, collected)
    if not stale:
        typer.echo("no stale waivers.")
        return
    verb = "would drop" if dry_run else "dropped"
    typer.echo(f"{verb} {len(stale)} stale waiver(s):")
    for w in stale:
        detail = f" {w.detail}" if w.detail else ""
        typer.echo(f"  - [{w.key}] [{w.engine}/{w.rule}] {w.qualified_name}{detail}")
    if not dry_run:
        save_waivers(collected.baseline_path, collected.store)
        typer.echo(f"wrote {collected.baseline_path}")


serve_app = typer.Typer(
    invoke_without_command=True,
    help="Run the local web viewer (FastAPI + Svelte SPA).",
)
app.add_typer(serve_app, name="serve")


@serve_app.callback()
def _serve_default(
    ctx: typer.Context,
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8765, "--port"),
) -> None:
    """Start the web viewer. `cdec serve parse` parses the CWD and opens it."""
    # A subcommand (e.g. `parse`) was given — let it handle everything.
    if ctx.invoked_subcommand is not None:
        return
    _run_server(host, port)


@serve_app.command("parse")
def serve_parse(
    path: Path = typer.Argument(
        Path("."),
        exists=True,
        file_okay=False,
        dir_okay=True,
        help="Source tree to parse (defaults to the current directory).",
    ),
    lang: Optional[str] = typer.Option(
        None,
        "--lang",
        help="python | csharp | typescript | svelte | odin | lua | julia. Auto-detected if omitted.",
    ),
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8765, "--port", help="Pass after `parse`, e.g. `serve parse --port 9000`."),
) -> None:
    """Start the viewer and open straight to the class diagram of a codebase.

    Shortcut for the parse-then-view flow: resolves the language (auto-detect
    when `--lang` is omitted, based on the file mix — any `.svelte` file wins,
    otherwise the most common of .py/.cs/.ts), then launches the server and
    opens the browser deep-linked to the rendered UML class diagram.
    """
    root = path.resolve()
    chosen = lang or detect_language(root)
    if chosen is None:
        raise typer.BadParameter(
            f"could not auto-detect a language under {root}; pass --lang explicitly"
        )
    if chosen not in (
        "python", "csharp", "typescript", "svelte", "odin", "lua", "julia",
    ):
        raise typer.BadParameter(f"unsupported language: {chosen}")

    url = f"http://{host}:{port}/?path={quote(str(root))}&lang={chosen}"
    typer.echo(f"serving {root} as {chosen}; opening the class diagram at {url}")
    _run_server(host, port, open_url=url)


@app.command()
def propose(
    model: Path = typer.Argument(
        ..., exists=True, dir_okay=False,
        help="Proposed target architecture (.json or .xmi), e.g. authored by an agent.",
    ),
    source: Optional[Path] = typer.Option(
        None, "--source", exists=True, file_okay=False, dir_okay=True,
        help="Source tree the proposal is for (falls back to .cdec/config.yaml).",
    ),
    lang: Optional[str] = typer.Option(
        None, "--lang", help="python | csharp | typescript | svelte | odin | lua | julia (auto-detected if omitted)."
    ),
    config_dir: Path = typer.Option(
        Path(".cdec"), "--config", help="`.cdec/` folder used to resolve omitted args."
    ),
    against: str = typer.Option(
        "source", "--against",
        help=(
            "Baseline for the diff: source (current code) | "
            "reference (.cdec/reference.xmi) | none."
        ),
    ),
    focus: str = typer.Option(
        "", "--focus",
        help="Comma-separated qualified class names; the viewer pre-filters to these.",
    ),
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8765, "--port"),
    no_browser: bool = typer.Option(
        False, "--no-browser", help="Don't open a browser tab; just push and print the URL."
    ),
) -> None:
    """Push a proposed architecture to the web viewer, diffed against a baseline.

    The review loop this enables: an agent writes/edits a model file (JSON is
    easiest), runs `cdec propose model.json --focus Billing,Invoice`, and the
    browser shows the proposal as a diff (green = still to build, red = to be
    removed). Re-running `propose` after editing the model refreshes any open
    viewer tab in place — no new tabs, no manual reload. Once agreed, lock it
    with `cdec reference set model.json`.

    If a `cdec serve` instance is already running on the port it is reused;
    otherwise a server is started (blocking) with the proposal pre-loaded.
    """
    if against not in ("source", "reference", "none"):
        raise typer.BadParameter("--against must be source|reference|none")

    source_path, chosen_lang, ref_path = _resolve_reference_inputs(
        source, lang, None, config_dir
    )
    proposal_proj = _load_model_cli(model)
    focus_q = quote(focus) if focus else ""

    from code_constraints.core.editor_io import project_to_json

    base_url = f"http://{host}:{port}"

    # --- fast path: a server is already running; push over HTTP and let any
    # open viewer tab hot-swap via its proposal polling.
    if _server_running(base_url):
        payload = project_to_json(proposal_proj)
        try:
            proj_info = _http_json(
                "POST", f"{base_url}/api/projects",
                {"path": str(source_path), "lang": chosen_lang},
            )
            push_url = (
                f"{base_url}/api/projects/{proj_info['id']}/proposal"
                f"?against={against}&focus={focus_q}"
            )
            result = _http_json("POST", push_url, payload)
        except Exception as exc:
            typer.echo(f"pushing proposal to running server failed: {exc}", err=True)
            raise typer.Exit(code=1) from exc
        view_url = (
            f"{base_url}/?xmi={result['id']}&project={result['project_id']}"
            f"&path={quote(f'proposal: {model}')}&lang={chosen_lang}&proposal=1"
            + (f"&focus={focus_q}" if focus_q else "")
        )
        typer.echo(
            f"pushed proposal #{result['seq']} for {source_path} (baseline: {against})"
        )
        if result["seq"] > 1:
            typer.echo("an open viewer tab will refresh automatically; URL:")
        typer.echo(view_url)
        if result["seq"] == 1 and not no_browser:
            import webbrowser

            webbrowser.open(view_url)
        typer.echo(f"when agreed, lock it with: cdec reference set {model}")
        return

    # --- no server yet: compute the diff in-process, pre-register it, and
    # start the server with the browser deep-linked to the proposal.
    import hashlib
    import uuid

    if against == "source":
        baseline = _parse_project(source_path, chosen_lang)
    elif against == "reference":
        if not ref_path.is_file():
            typer.echo(f"reference XMI not found: {ref_path}", err=True)
            raise typer.Exit(code=2)
        baseline = _load_model_cli(ref_path)
    else:
        baseline = None

    if baseline is not None:
        try:
            annotated = diff_projects(baseline, proposal_proj)
        except ValueError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=2) from exc
    else:
        annotated = proposal_proj

    from code_constraints.web.app import ProjectInfo, XmiInfo, _project_cache, _registry

    project_id = hashlib.sha1(
        f"{source_path}|{chosen_lang}".encode("utf-8")
    ).hexdigest()[:12]
    xmi_id = uuid.uuid4().hex[:12]
    write_project(annotated, _project_cache(project_id) / f"{xmi_id}.xmi")
    _registry.register(
        ProjectInfo(id=project_id, path=str(source_path), lang=chosen_lang)
    )
    _registry.register_xmi(XmiInfo(id=xmi_id, project_id=project_id))
    focus_list = [f.strip() for f in focus.split(",") if f.strip()]
    _registry.record_proposal(project_id, xmi_id, focus_list)

    view_url = (
        f"{base_url}/?xmi={xmi_id}&project={project_id}"
        f"&path={quote(f'proposal: {model}')}&lang={chosen_lang}&proposal=1"
        + (f"&focus={focus_q}" if focus_q else "")
    )
    typer.echo(f"proposal loaded (baseline: {against}); serving at {view_url}")
    typer.echo(f"iterate with: cdec propose {model}   (refreshes the open tab)")
    typer.echo(f"when agreed, lock it with: cdec reference set {model}")
    _run_server(host, port, open_url=None if no_browser else view_url)


lock_app = typer.Typer(
    help=(
        "Freeze class/function implementations so they cannot change (Engine C). "
        "Identity is AST-derived, so moving or reformatting code never trips a lock."
    )
)
app.add_typer(lock_app, name="lock")


@lock_app.command("list")
def lock_list(
    source: Optional[Path] = typer.Argument(
        None, exists=True, file_okay=False, dir_okay=True,
        help="Source tree to scan (falls back to .cdec/config.yaml `source`).",
    ),
    lang: Optional[str] = typer.Option(None, "--lang", help="python | csharp | odin | lua | julia (languages with a lock fingerprinter)."),
    config_dir: Path = typer.Option(Path(".cdec"), "--config", help="`.cdec/` folder."),
    lockfile: Optional[Path] = typer.Option(
        None, "--lockfile", help="Ledger path (default: .cdec/locks.yaml)."
    ),
    all_targets: bool = typer.Option(
        False, "--all", help="List every lockable element, not just the locked ones."
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Show which implementations are frozen, and whether each still matches."""
    from code_constraints.lock import LockOptions, collect_targets, is_locked_target

    ctx = _lock_context(source, lang, config_dir, lockfile)
    targets = _collect_lock_targets(ctx.source, ctx.lang, ctx.options)

    rows: list[dict] = []
    for target in sorted(targets, key=lambda t: t.target):
        locked = is_locked_target(target, ctx.options.patterns)
        if not locked and not all_targets:
            continue
        entry = ctx.entries.get(target.target)
        if not locked:
            state = "unlocked"
        elif entry is None:
            state = "not-baselined"
        elif entry.digest != target.digest:
            state = "CHANGED"
        else:
            state = "ok"
        rows.append(
            {
                "target": target.target,
                "kind": target.kind,
                "state": state,
                "file": target.file,
                "line": target.line,
                "declared": target.declared,
                "digest": target.digest[:12],
                "reason": (entry.reason if entry else "") or target.reason,
                "locked_by": entry.locked_by if entry else "",
            }
        )

    # Ledger entries with no matching element are invisible above; surface them.
    seen = {r["target"] for r in rows}
    for name, entry in sorted(ctx.entries.items()):
        if name in seen:
            continue
        rows.append(
            {
                "target": name, "kind": entry.kind, "state": "MISSING-FROM-SOURCE",
                "file": entry.file, "line": 0, "declared": False,
                "digest": entry.digest[:12], "reason": entry.reason,
                "locked_by": entry.locked_by,
            }
        )

    if json_output:
        import json as _json

        typer.echo(_json.dumps({"locks": rows}, indent=2, sort_keys=True))
        return

    if not rows:
        typer.echo(
            "no locked implementations.\n"
            "Tag a class or function with @locked (Python) / [Locked] (C#), then run "
            "`cdec lock set`."
        )
        return
    width = max(len(r["target"]) for r in rows)
    for r in rows:
        via = "tag" if r["declared"] else "glob"
        typer.echo(
            f"{r['state']:<20} {r['target']:<{width}}  {r['kind']:<8} ({via})  "
            f"{r['file']}:{r['line']}"
        )
        if r["reason"]:
            typer.echo(f"{'':<20} reason: {r['reason']}")
    typer.echo(f"\n{len(rows)} entr(ies).")


@lock_app.command("check")
def lock_check(
    source: Optional[Path] = typer.Argument(
        None, exists=True, file_okay=False, dir_okay=True,
        help="Source tree to verify (falls back to .cdec/config.yaml `source`).",
    ),
    lang: Optional[str] = typer.Option(None, "--lang", help="python | csharp | odin | lua | julia (languages with a lock fingerprinter)."),
    config_dir: Path = typer.Option(Path(".cdec"), "--config", help="`.cdec/` folder."),
    lockfile: Optional[Path] = typer.Option(
        None, "--lockfile", help="Ledger path (default: .cdec/locks.yaml)."
    ),
    bypass: bool = typer.Option(
        False, "--bypass", help="Report but do not fail. Prints an audit banner."
    ),
    bypass_reason: str = typer.Option(
        "", "--bypass-reason", help="Why locks are being bypassed (recorded in output)."
    ),
    format: str = typer.Option("human", "--format", help="human | json"),
    json_out: Optional[Path] = typer.Option(None, "--json-out", help="Write a JSON report."),
) -> None:
    """Fail (exit 1) if any frozen implementation changed.

    Catches five things: an edited body, a deleted element, a deleted @locked
    tag, a tag that was never baselined, and a digest-algorithm change.
    """
    if format not in ("human", "json"):
        raise typer.BadParameter(f"unknown format: {format}")

    ctx = _lock_context(source, lang, config_dir, lockfile)
    report = _run_lock_check(ctx, bypass=bypass, bypass_reason=bypass_reason)

    from code_constraints.lock import format_report, report_to_json

    if format == "human":
        typer.echo(format_report(report), nl=False)
    else:
        import json as _json

        typer.echo(_json.dumps(report_to_json(report), indent=2, sort_keys=True))

    if json_out is not None:
        import json as _json

        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(
            _json.dumps(report_to_json(report), indent=2, sort_keys=True), encoding="utf-8"
        )
        typer.echo(f"wrote {json_out}")

    if not report.ok:
        raise typer.Exit(code=1)


@lock_app.command("set")
def lock_set(
    source: Optional[Path] = typer.Argument(
        None, exists=True, file_okay=False, dir_okay=True,
        help="Source tree to fingerprint (falls back to .cdec/config.yaml `source`).",
    ),
    lang: Optional[str] = typer.Option(None, "--lang", help="python | csharp | odin | lua | julia (languages with a lock fingerprinter)."),
    config_dir: Path = typer.Option(Path(".cdec"), "--config", help="`.cdec/` folder."),
    lockfile: Optional[Path] = typer.Option(
        None, "--lockfile", help="Ledger path (default: .cdec/locks.yaml)."
    ),
    target: list[str] = typer.Option(
        [], "--target", help="Restrict to matching qualified-name globs (repeatable)."
    ),
    force: bool = typer.Option(
        False, "--force",
        help="Re-baseline implementations that have DRIFTED, and drop stale entries. "
             "This is the privileged operation — it accepts a change to frozen code.",
    ),
    reason: str = typer.Option("", "--reason", help="Why these locks were (re)set."),
    owner: str = typer.Option("", "--owner", help="Who approved (defaults to the OS user)."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Report without writing."),
) -> None:
    """Record the current implementations as the approved baseline.

    Without `--force` this only *adds* locks for newly tagged elements — it can
    never erase evidence that frozen code changed, so it is safe for anyone to
    run. Accepting a change to an already-locked implementation requires
    `--force`, which shows up as a reviewable diff on the ledger; gate that file
    with CODEOWNERS to keep re-baselining a lead-only action.
    """
    from code_constraints.lock import update_locks, write_locks

    ctx = _lock_context(source, lang, config_dir, lockfile)
    try:
        entries, result = update_locks(
            ctx.source, ctx.lang, ctx.entries, ctx.options,
            only=target, force=force, reason=reason, owner=owner,
        )
    except Exception as exc:  # noqa: BLE001 - surfaced verbatim to the user
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    for entry in result.added:
        typer.echo(f"+ locked   {entry.target}  ({entry.kind}, {entry.digest[:12]})")
    for entry in result.updated:
        typer.echo(f"~ rebased  {entry.target}  ({entry.kind}, {entry.digest[:12]})")
    for entry in result.removed:
        typer.echo(f"- released {entry.target}")

    if result.blocked:
        typer.echo("")
        typer.echo(
            f"{len(result.blocked)} locked implementation(s) have CHANGED and were left "
            f"untouched:"
        )
        for v in result.blocked:
            typer.echo(f"  - {v.target} — {v.file}:{v.line}")
        typer.echo(
            "\nRe-run with --force to accept these changes as the new baseline "
            "(a lead's call), or revert the code."
        )

    if result.stale:
        typer.echo("")
        typer.echo(
            f"{len(result.stale)} ledger entr(ies) are still locked but their element "
            f"is gone or has lost its tag:"
        )
        for entry in result.stale:
            typer.echo(f"  - {entry.target}")
        typer.echo(
            "\nThese remain locked and `cdec lock check` will keep failing. Restore the "
            "code, or release them with `cdec lock remove --target <name>` "
            "(or `cdec lock set --force` to prune)."
        )

    if dry_run:
        typer.echo("\n(dry run — nothing written)")
    elif result.changed:
        write_locks(ctx.lockfile, entries.values())
        typer.echo(f"\nwrote {ctx.lockfile} ({len(entries)} lock(s))")
    elif result.clean:
        typer.echo(f"{result.unchanged} lock(s) already up to date; nothing to write.")

    if not result.clean:
        raise typer.Exit(code=1)


@lock_app.command("remove")
def lock_remove(
    target: list[str] = typer.Option(
        ..., "--target", help="Qualified-name glob(s) to release (repeatable)."
    ),
    config_dir: Path = typer.Option(Path(".cdec"), "--config", help="`.cdec/` folder."),
    lockfile: Optional[Path] = typer.Option(
        None, "--lockfile", help="Ledger path (default: .cdec/locks.yaml)."
    ),
) -> None:
    """Release locks from the ledger.

    Removing the ledger entry is only half of unlocking — also delete the
    `@locked` / `[Locked]` tag from the source, or the next `cdec lock check`
    reports the element as not baselined.
    """
    from code_constraints.lock import load_locks, resolve_entries_for_removal, write_locks
    from code_constraints.lock.store import LOCKS_FILENAME as _LOCKS_FILENAME

    path = lockfile or (config_dir / _LOCKS_FILENAME)
    entries = _load_locks_cli(path)
    doomed = resolve_entries_for_removal(entries, target)
    if not doomed:
        typer.echo(f"no ledger entries match {', '.join(target)}")
        raise typer.Exit(code=1)
    for entry in doomed:
        del entries[entry.target]
        typer.echo(f"- released {entry.target}")
    write_locks(path, entries.values())
    typer.echo(f"wrote {path} ({len(entries)} lock(s) remaining)")
    typer.echo(
        "Remember to delete the corresponding @locked / [Locked] tag from the source."
    )


reference_app = typer.Typer(
    help="Snapshot, test against, and visualise the architecture reference."
)
app.add_typer(reference_app, name="reference")


@reference_app.command("test")
def reference_test(
    source: Optional[Path] = typer.Argument(
        None,
        exists=True,
        file_okay=False,
        dir_okay=True,
        help="Source tree to parse (falls back to .cdec/config.yaml `source`).",
    ),
    reference: Optional[Path] = typer.Option(
        None, "--reference", help="Reference XMI (default: .cdec/reference.xmi)."
    ),
    lang: Optional[str] = typer.Option(
        None, "--lang", help="python | csharp | typescript | svelte | odin | lua | julia (auto-detected if omitted)."
    ),
    config_dir: Path = typer.Option(
        Path(".cdec"), "--config", help="`.cdec/` folder used to resolve omitted args."
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Emit JSON instead of human-readable text."
    ),
    output: Optional[Path] = typer.Option(
        None, "--output", help="Also write the report to this file."
    ),
) -> None:
    """Fail (exit 1) if the current code deviates structurally from the reference XMI.

    Reports every structural deviation — added/removed classes, added/removed
    properties or methods, changed method signatures or return types, changed
    access levels and modifiers (static/abstract/readonly), changed class kind,
    and changed base classes. Intended as a CI gate to reject non-conforming PRs.
    """
    source_path, chosen_lang, ref_path = _resolve_reference_inputs(
        source, lang, reference, config_dir
    )
    if not ref_path.is_file():
        typer.echo(f"reference XMI not found: {ref_path}", err=True)
        raise typer.Exit(code=2)

    from code_constraints.reference import compare_to_reference, format_human, to_json

    reference_proj = _load_model_cli(ref_path)
    current = _parse_project(source_path, chosen_lang)
    try:
        deviations = compare_to_reference(reference_proj, current)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    if json_output:
        import json as _json

        report_text = _json.dumps(to_json(deviations), indent=2) + "\n"
    else:
        report_text = format_human(deviations)
    typer.echo(report_text, nl=False)

    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(report_text, encoding="utf-8")
        typer.echo(f"wrote {output}")

    if deviations:
        raise typer.Exit(code=1)


@reference_app.command("update")
def reference_update(
    source: Optional[Path] = typer.Argument(
        None,
        exists=True,
        file_okay=False,
        dir_okay=True,
        help="Source tree to snapshot (falls back to .cdec/config.yaml `source`).",
    ),
    reference: Optional[Path] = typer.Option(
        None, "--reference", help="Destination XMI (default: .cdec/reference.xmi)."
    ),
    lang: Optional[str] = typer.Option(
        None, "--lang", help="python | csharp | typescript | svelte | odin | lua | julia (auto-detected if omitted)."
    ),
    config_dir: Path = typer.Option(
        Path(".cdec"), "--config", help="`.cdec/` folder used to resolve omitted args."
    ),
) -> None:
    """Snapshot the current architecture into the reference XMI."""
    source_path, chosen_lang, ref_path = _resolve_reference_inputs(
        source, lang, reference, config_dir
    )
    proj = _parse_project(source_path, chosen_lang)
    _save_model_cli(proj, ref_path)
    typer.echo(f"wrote {ref_path}")


@reference_app.command("set")
def reference_set(
    model: Path = typer.Argument(
        ..., exists=True, dir_okay=False,
        help="Model file to promote (.json or .xmi) — e.g. an agreed proposal.",
    ),
    reference: Optional[Path] = typer.Option(
        None, "--reference", help="Destination reference file (default: .cdec/reference.xmi)."
    ),
    config_dir: Path = typer.Option(
        Path(".cdec"), "--config", help="`.cdec/` folder used to resolve the destination."
    ),
) -> None:
    """Lock an authored model as the target architecture.

    Takes a hand-written / agent-written model file (JSON or XMI) and writes it
    to the project's reference XMI, so `cdec check` and `cdec reference test`
    immediately start constraining development against it. This is the
    "accept the proposal" step of the propose -> review -> lock workflow.
    """
    proj = _load_model_cli(model)
    if reference is not None:
        ref_path = reference
    else:
        try:
            cfg = load_project_config(config_dir)
            ref_path = cfg.reference or (config_dir / REFERENCE_FILENAME)
        except ConfigError:
            ref_path = config_dir / REFERENCE_FILENAME
    ref_path.parent.mkdir(parents=True, exist_ok=True)
    _save_model_cli(proj, ref_path)
    n_classes = sum(1 for _ in proj.iter_classes())
    typer.echo(f"locked {model} as target architecture -> {ref_path} ({n_classes} classes)")


@reference_app.command("show")
def reference_show(
    source: Optional[Path] = typer.Argument(
        None,
        exists=True,
        file_okay=False,
        dir_okay=True,
        help="Source tree to compare (falls back to .cdec/config.yaml `source`).",
    ),
    reference: Optional[Path] = typer.Option(
        None, "--reference", help="Reference XMI (default: .cdec/reference.xmi)."
    ),
    lang: Optional[str] = typer.Option(
        None, "--lang", help="python | csharp | typescript | svelte | odin | lua | julia (auto-detected if omitted)."
    ),
    config_dir: Path = typer.Option(
        Path(".cdec"), "--config", help="`.cdec/` folder used to resolve omitted args."
    ),
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8765, "--port"),
) -> None:
    """Open the web viewer to a diff of the current code against the reference (target) architecture."""
    import uuid

    source_path, chosen_lang, ref_path = _resolve_reference_inputs(
        source, lang, reference, config_dir
    )
    if not ref_path.is_file():
        typer.echo(f"reference XMI not found: {ref_path}", err=True)
        raise typer.Exit(code=2)

    reference_proj = _load_model_cli(ref_path)
    current = _parse_project(source_path, chosen_lang)
    try:
        # The reference is the *target* architecture and the codebase is the
        # *current* state, so the codebase is the old side and the reference the
        # new side: elements only in the reference render as green additions
        # ("the code still needs to grow this"), elements only in the code as
        # red removals. This is intentionally the inverse of `diff-vs-xmi` /
        # `reference test`, where the reference is the old baseline.
        annotated = diff_projects(current, reference_proj)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    # Pre-register the annotated diff in the in-process web registry (uvicorn
    # imports `code_constraints.web.app` in this same process, so the module-level registry
    # is shared). The `u`-prefixed project id marks it synthetic in the UI.
    from code_constraints.web.app import ProjectInfo, XmiInfo, _project_cache, _registry

    project_id = "u" + uuid.uuid4().hex[:11]
    xmi_id = uuid.uuid4().hex[:12]
    label = f"reference diff: {source_path} -> {ref_path.name}"
    write_project(annotated, _project_cache(project_id) / f"{xmi_id}.xmi")
    # Register the *real* source directory as the project path so the views /
    # git / layer endpoints (which resolve `.cdec/` via `_find_cdec_dir(info.path)`)
    # work. The human-readable `label` is only for display and rides the URL.
    _registry.register(ProjectInfo(id=project_id, path=str(source_path), lang=chosen_lang))
    _registry.register_xmi(XmiInfo(id=xmi_id, project_id=project_id))

    url = (
        f"http://{host}:{port}/?xmi={xmi_id}&project={project_id}"
        f"&path={quote(label)}&lang={chosen_lang}"
    )
    typer.echo(f"comparing {source_path} (current) against target {ref_path}; opening {url}")
    _run_server(host, port, open_url=url)


# ---------- helpers ----------

def _server_running(base_url: str) -> bool:
    """True if a code-constraints server answers at `base_url`."""
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(f"{base_url}/api/projects", timeout=1.5):
            return True
    except (urllib.error.URLError, OSError, TimeoutError):
        return False


def _http_json(method: str, url: str, payload: Optional[dict] = None) -> dict:
    """Minimal JSON-over-HTTP client (stdlib only). Raises on non-2xx."""
    import json as _json
    import urllib.error
    import urllib.request

    data = _json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("content-type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{exc.code} {exc.reason}: {detail}") from exc
    return _json.loads(body or b"null")


def _load_model_cli(path: Path):
    """`load_model` with typer-friendly error reporting."""
    try:
        return load_model(path)
    except UnsupportedModelFormat as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(f"could not read model {path}: {exc}", err=True)
        raise typer.Exit(code=2) from exc


def _save_model_cli(project, path: Path) -> None:
    try:
        save_model(project, path)
    except UnsupportedModelFormat as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc


@dataclass
class _LockContext:
    """Everything `cdec lock` / `cdec check --lock` needs, resolved once."""

    source: Path
    lang: str
    lockfile: Path
    entries: dict
    options: object  # code_constraints.lock.LockOptions


def _lock_context(
    source: Optional[Path],
    lang: Optional[str],
    config_dir: Path,
    lockfile: Optional[Path],
) -> _LockContext:
    """Resolve source / language / ledger path from explicit args with a
    `.cdec/config.yaml` fallback, mirroring `_resolve_reference_inputs`."""
    from code_constraints.lint.config import LOCKS_FILENAME
    from code_constraints.lock import LockOptions

    cfg = None
    try:
        cfg = load_project_config(config_dir)
    except ConfigError:
        cfg = None

    source_path = source.resolve() if source else (cfg.source if cfg else None)
    if source_path is None:
        raise typer.BadParameter(
            "no source given and none found in .cdec/config.yaml; pass a SOURCE "
            "argument or run from a scaffolded project (cdec init)."
        )
    chosen_lang = lang or (cfg.language if cfg else None) or detect_language(source_path)
    if chosen_lang is None:
        raise typer.BadParameter(
            f"could not determine a language for {source_path}; pass --lang explicitly."
        )

    if lockfile is not None:
        lock_path = lockfile
    elif cfg is not None and cfg.lock.lockfile is not None:
        lock_path = cfg.lock.lockfile
    else:
        lock_path = config_dir / LOCKS_FILENAME

    options = LockOptions(
        include_docstrings=cfg.lock.include_docstrings if cfg else False,
        patterns=list(cfg.lock.targets) if cfg else [],
    )
    return _LockContext(
        source=source_path,
        lang=chosen_lang,
        lockfile=lock_path,
        entries=_load_locks_cli(lock_path),
        options=options,
    )


# ---------- waiver / review helpers ----------

def _filter_findings(
    findings: list[Finding], store: WaiverStore
) -> tuple[list[Finding], list[Finding]]:
    """Split conformance findings into (reported, silenced-by-baseline)."""
    kept: list[Finding] = []
    silenced: list[Finding] = []
    for f in findings:
        target = silenced if store.matches("enforce", f.rule, f.qualified_name, f.detail) else kept
        target.append(f)
    return kept, silenced


def _record_findings(baseline_path: Path, source: Path, lang: str) -> int:
    """Accept every current conformance finding into the ledger. Returns how
    many are recorded."""
    from code_constraints.enforce import enforce as run_enforce
    from code_constraints.waivers import Waiver, load_waivers, now_stamp, save_waivers
    from code_constraints.waivers.store import default_actor

    findings = run_enforce(source, lang)
    store = load_waivers(baseline_path)
    stamp = now_stamp()
    actor = default_actor()
    existing = {w.key: w for w in store.for_engine("enforce")}
    store.replace_engine(
        "enforce",
        [
            Waiver(
                engine="enforce",
                rule=f.rule,
                qualified_name=f.qualified_name,
                detail=f.detail,
                reason=existing[f.key()].reason if f.key() in existing else "",
                added=existing[f.key()].added if f.key() in existing else stamp,
                added_by=existing[f.key()].added_by if f.key() in existing else actor,
            )
            for f in findings
        ],
    )
    save_waivers(baseline_path, store)
    return len(findings)


def _collect_issues_cli(
    config_dir: Path,
    *,
    source: Optional[Path] = None,
    reference: Optional[Path] = None,
    base_ref: Optional[str] = None,
    repo: Path = Path("."),
) -> "Collected":
    """Run every engine and return the keyed issue list, with typer-friendly
    errors. The baseline-resolution options mirror `cdec check` exactly — the
    keys only line up if both commands look at the same diff."""
    from code_constraints.lint.pipeline import PipelineError
    from code_constraints.waivers import CollectOptions, collect_issues
    from code_constraints.waivers.store import WaiverFileError

    try:
        return collect_issues(
            config_dir,
            CollectOptions(
                source=source,
                reference=reference,
                base_ref=base_ref,
                repo=repo,
            ),
        )
    except (ConfigError, PipelineError, WaiverFileError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc


def _load_waivers_cli(path: Path) -> "WaiverStore":
    from code_constraints.waivers import load_waivers
    from code_constraints.waivers.store import WaiverFileError

    try:
        return load_waivers(path)
    except WaiverFileError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc


def _read_review_text(file: Path) -> str:
    if str(file) == "-":
        import sys

        return sys.stdin.read()
    if not file.is_file():
        typer.echo(f"no such file: {file}", err=True)
        raise typer.Exit(code=2)
    return file.read_text(encoding="utf-8")


def _write_or_echo(text: str, out: Optional[Path]) -> None:
    if out is None:
        typer.echo(text, nl=False)
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    typer.echo(f"wrote {out}")


def _issue_to_json(issue: "Issue") -> dict[str, object]:
    return {
        "key": issue.key,
        "engine": issue.engine,
        "rule": issue.rule,
        "qualifiedName": issue.qualified_name,
        "detail": issue.detail,
        "message": issue.message,
        "severity": issue.severity,
        "file": issue.file,
        "line": issue.line,
        "waived": issue.waived,
        "waivable": issue.waivable,
    }


def _report_apply(result: "ApplyResult", baseline_path: Path, *, dry_run: bool) -> None:
    """Print what an allow/patch/remove did — or would do."""
    would = "would " if dry_run else ""
    for issue in result.allowed:
        detail = f" {issue.detail}" if issue.detail else ""
        typer.echo(f"{would}allow [{issue.key}] {issue.rule} {issue.qualified_name}{detail}")
    for waiver in result.removed:
        typer.echo(f"{would}remove [{waiver.key}] {waiver.rule} {waiver.qualified_name}")
    for issue in result.already_waived:
        typer.echo(f"already allowed: [{issue.key}] {issue.qualified_name}")
    for key in result.not_waived:
        typer.echo(f"not currently allowed, nothing to remove: {key}", err=True)
    for key in result.malformed:
        typer.echo(f"not a valid issue key: {key!r} (expected e.g. V-1A2B3C4D)", err=True)
    for key in result.unknown:
        typer.echo(
            f"unknown key {key}: no issue with that key is being reported. "
            f"Re-run `cdec check` — the report may be out of date.",
            err=True,
        )
    for _key, message in result.refused:
        typer.echo(message, err=True)
    for problem in result.problems:
        typer.echo(problem, err=True)

    if not result.changed:
        typer.echo("no changes to the baseline.")
    elif dry_run:
        typer.echo(f"dry run — {baseline_path} not written.")
    else:
        typer.echo(f"wrote {baseline_path}")


def _exit_on_apply_failure(result: "ApplyResult", *, ignore_unknown: bool = False) -> None:
    failed = bool(result.refused or result.malformed or result.problems)
    if result.unknown and not ignore_unknown:
        failed = True
    if failed:
        raise typer.Exit(code=1)


def _load_locks_cli(path: Path) -> dict:
    from code_constraints.lock import LockfileError, load_locks

    try:
        return load_locks(path)
    except LockfileError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc


def _collect_lock_targets(source: Path, lang: str, options):
    from code_constraints.lock import UnsupportedLockLanguage, collect_targets

    try:
        return collect_targets(source, lang, options)
    except UnsupportedLockLanguage as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc


def _run_lock_check(ctx: _LockContext, *, bypass: bool, bypass_reason: str):
    from code_constraints.lock import UnsupportedLockLanguage, check_locks

    try:
        return check_locks(
            ctx.source, ctx.lang, ctx.entries, ctx.options,
            bypass=bypass, bypass_reason=bypass_reason,
        )
    except UnsupportedLockLanguage as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc


def _resolve_reference_inputs(
    source: Optional[Path],
    lang: Optional[str],
    reference: Optional[Path],
    config_dir: Path,
) -> tuple[Path, str, Path]:
    """Resolve (source_path, language, reference_path) from explicit args with a
    `.cdec/` fallback. Explicit args always win; `.cdec/config.yaml` fills the gaps
    and `.cdec/reference.xmi` is the conventional reference location."""
    cfg = None
    if source is None or lang is None or reference is None:
        try:
            cfg = load_project_config(config_dir)
        except ConfigError:
            cfg = None

    source_path = source.resolve() if source else (cfg.source if cfg else None)
    if source_path is None:
        raise typer.BadParameter(
            "no source given and none found in .cdec/config.yaml; pass a SOURCE "
            "argument or run from a scaffolded project (cdec init)."
        )

    chosen_lang = lang or (cfg.language if cfg else None) or detect_language(source_path)
    if chosen_lang is None:
        raise typer.BadParameter(
            f"could not determine a language for {source_path}; pass --lang explicitly."
        )
    if chosen_lang not in (
        "python", "csharp", "typescript", "svelte", "odin", "lua", "julia",
    ):
        raise typer.BadParameter(f"unsupported language: {chosen_lang}")

    if reference is not None:
        ref_path = reference
    elif cfg is not None and cfg.reference is not None:
        ref_path = cfg.reference
    else:
        ref_path = config_dir / REFERENCE_FILENAME

    return source_path, chosen_lang, ref_path


def _run_server(host: str, port: int, open_url: Optional[str] = None) -> None:
    """Run uvicorn (blocking). If `open_url` is set, pop the browser once the
    server has had a moment to bind."""
    import uvicorn

    if open_url is not None:
        import threading
        import webbrowser

        threading.Timer(1.5, lambda: webbrowser.open(open_url)).start()

    uvicorn.run("code_constraints.web.app:app", host=host, port=port, reload=False)

def _parse_project(path: Path, lang: str):
    from code_constraints.lint.pipeline import PipelineError, parse_source

    try:
        return parse_source(path, lang)
    except PipelineError as exc:
        raise typer.BadParameter(str(exc)) from exc


def _emit(project, diagram: str, name: Optional[str]) -> Optional[str]:
    if diagram == "class":
        return emit_class_diagram(project)
    if diagram == "package":
        return emit_package_diagram(project)
    if diagram == "activity":
        if not name:
            raise typer.BadParameter("--name required for activity diagram")
        act = next((a for a in project.activities if a.name == name), None)
        return emit_activity_diagram(act) if act else None
    if diagram == "sequence":
        if not name:
            raise typer.BadParameter("--name required for sequence diagram")
        seq = next((s for s in project.sequences if s.name == name), None)
        return emit_sequence_diagram(seq) if seq else None
    raise typer.BadParameter(f"unknown diagram type: {diagram}")


def _checkout_revision(repo: Repo, ref: str, dest: Path) -> Path:
    """Copy the tree at `ref` into `dest` (avoids touching the working tree)."""
    from code_constraints.lint.pipeline import checkout_revision

    return checkout_revision(repo, ref, dest)


def _resolve_baseline_and_diff(
    *,
    head_proj,
    cfg_language: str,
    config_dir: Path,
    explicit_reference: Optional[Path],
    explicit_base_ref: Optional[str],
    repo_path: Path,
    default_reference: Optional[Path],
):
    """Returns (project_for_rules, has_diff, baseline_project). When no baseline
    is available, returns the head project unchanged with has_diff=False and a
    None baseline (so diff-scope rules will be skipped by the engine).

    Delegates to `lint.pipeline` so `cdec baseline` resolves the baseline the
    same way — the review keys only line up if both see the same diff."""
    from code_constraints.lint.pipeline import PipelineError, resolve_baseline

    try:
        return resolve_baseline(
            head_proj=head_proj,
            lang=cfg_language,
            config_dir=config_dir,
            explicit_reference=explicit_reference,
            explicit_base_ref=explicit_base_ref,
            repo_path=repo_path,
            default_reference=default_reference,
        )
    except PipelineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc


if __name__ == "__main__":
    app()
