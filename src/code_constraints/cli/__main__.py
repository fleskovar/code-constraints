"""`cdec` command-line entry point."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Optional, cast
from urllib.parse import quote

import typer
from git import Repo

from code_constraints.cli.detect import detect_language

from code_constraints.core.diff import diff_projects
from code_constraints.core.model import SUPPORTED_LANGUAGES, SourceLanguage
from code_constraints.core.model_io import UnsupportedModelFormat, load_model, save_model
from code_constraints.core.xmi_writer import write_project
from code_constraints.lint.baseline import load_baseline, write_baseline
from code_constraints.lint.config import (
    REFERENCE_FILENAME,
    ConfigError,
    load_project_config,
    load_rules,
)
from code_constraints.lint.engine import run_checks
from code_constraints.lint.rules.base import Severity

if TYPE_CHECKING:
    # Annotation-only: the review machinery and the engine internals are
    # imported lazily inside the commands that use them, so `cdec parse`
    # doesn't pay for any of it.
    from collections.abc import Callable

    from code_constraints.lint.config import LoadedRules
    from code_constraints.lint.engine import SourceContext
    from code_constraints.lint.report import Report
    from code_constraints.lint.rules.base import RuleContext
    from code_constraints.waivers import ApplyResult, Collected, Issue, WaiverStore

_LANG_HELP = "python | csharp | typescript | svelte | odin | lua | julia"

app = typer.Typer(
    help=(
        "code-constraints (cdec) — enforce architectural and implementation "
        "constraints on a codebase. "
        "Model it with parse / convert / diff. Gate it with `cdec check`, which "
        "runs every rule in .cdec/rules.yaml — architectural rules, source-tag "
        "conformance, implementation locks and the reference-architecture gate "
        "alike. Keep it moving with `cdec exceptions`, which records the "
        "violations you accept and why."
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
    migrate: bool = typer.Option(
        False, "--migrate",
        help="Fold an existing config.yaml / baseline.yaml / locks.yaml into "
             "rules.yaml and delete them, instead of scaffolding.",
    ),
) -> None:
    """Scaffold `.cdec/rules.yaml` and a reference snapshot.

    One file holds the project settings, the rules, the exceptions granted and
    the digests of frozen implementations, so there is one thing to commit and
    one diff to review. `--migrate` converts a project that still has the old
    per-concern files.
    """
    from code_constraints.cli.scaffold import (
        SUPPORTED_LANGS,
        ScaffoldError,
        init_cdec_config,
        migrate_cdec_config,
    )

    if migrate:
        try:
            written, removed = migrate_cdec_config(config_dir)
        except ScaffoldError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc
        if not written and not removed:
            typer.echo(f"{config_dir}: nothing to migrate — already on rules.yaml.")
            return
        for path in written:
            typer.echo(f"wrote {path}")
        for path in removed:
            typer.echo(f"removed {path} (its content now lives in rules.yaml)")
        typer.echo("Review the diff, then commit .cdec/rules.yaml.")
        return

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


AUTO_ACCEPT_CHOICES = ("rules", "locks", "reference", "all")


@app.command()
def check(
    config_dir: Path = typer.Option(
        Path(".cdec"), "--config", help="`.cdec/` folder holding rules.yaml."
    ),
    source: Optional[Path] = typer.Option(
        None, "--source", help="Override the source tree from rules.yaml."
    ),
    lang: Optional[str] = typer.Option(
        None, "--lang", help="Override the language from rules.yaml."
    ),
    rules_file: list[str] = typer.Option(
        [], "--rules-file", "-R", metavar="NAME",
        help=(
            "Run only the rules in these files from `.cdec/rules/` (name, with "
            "or without the .yaml). Default: rules.yaml plus every file in "
            "`.cdec/rules/`. Repeatable or comma-separated."
        ),
    ),
    base_ref: Optional[str] = typer.Option(
        None, "--base-ref", help="Git ref to use as the diff baseline (parsed live)."
    ),
    reference: Optional[Path] = typer.Option(
        None, "--reference", help="Override the reference model (default: .cdec/reference.xmi)."
    ),
    repo: Path = typer.Option(Path("."), "--repo", help="Git repo root (only used with --base-ref)."),
    format: str = typer.Option("human", "--format", help="human | json"),
    json_out: Optional[Path] = typer.Option(None, "--json-out", help="Also write a JSON report."),
    log_out: Optional[Path] = typer.Option(None, "--log-out", help="Also tee the human report to a file."),
    fail_on: str = typer.Option("error", "--fail-on", help="error | warning | none"),
    automatic_exceptions: list[str] = typer.Option(
        [], "--automatic-exceptions", "-A", metavar="WHAT",
        help=(
            "Accept the code as it stands now instead of failing on it. "
            "rules = grandfather every current violation into `exceptions:`; "
            "locks = record digests for newly @locked code; "
            "reference = re-snapshot reference.xmi; "
            "all = every one of those. Repeatable or comma-separated."
        ),
    ),
    force: bool = typer.Option(
        False, "--force",
        help="With `--automatic-exceptions locks`, also re-baseline implementations "
             "that have CHANGED and drop released entries. This is the privileged "
             "operation: it accepts a change to frozen code.",
    ),
    bypass_locks: bool = typer.Option(
        False, "--bypass-locks",
        help="Report lock violations but do not fail on them. Prints an audit banner "
             "and sets summary.bypassed in the JSON report.",
    ),
    bypass_reason: str = typer.Option(
        "", "--bypass-reason", help="Why locks are being bypassed (recorded in the output)."
    ),
) -> None:
    """Check the project against every rule in `.cdec/rules.yaml`.

    Rules may also be split across `.cdec/rules/*.yaml`; all of them run by
    default, and `--rules-file` narrows the run to the files you name.

    This is the whole gate. Configured architectural rules, source-tag
    conformance, implementation locks and the reference-architecture gate are
    all rule types in that one file, so there is one command to run, one report
    to read, one exit code for CI, and one place to record an exception.
    """
    if format not in ("human", "json"):
        raise typer.BadParameter(f"unknown format: {format}")
    try:
        fail_on_sev = Severity(fail_on)
    except ValueError as exc:
        raise typer.BadParameter(f"--fail-on must be error|warning|none, got {fail_on!r}") from exc
    accept = _parse_auto_accept(automatic_exceptions)

    cfg = _load_config_cli(config_dir)
    source_path = source.resolve() if source else cfg.source
    language = lang or cfg.language
    if language not in SUPPORTED_LANGUAGES:
        raise typer.BadParameter(f"unsupported language: {language}")
    selected = _split_csv(rules_file)
    loaded = _load_rules_cli(config_dir, selected)
    _warn_about_legacy_files(config_dir)

    from code_constraints.lint.engine import SourceContext

    ctx_info = SourceContext(
        source=source_path,
        language=language,
        config_dir=config_dir,
        reference_path=reference or cfg.reference_path,
    )

    def run(*, filtered: bool) -> "Report":
        """Parse, resolve the baseline, and run every rule. `filtered` applies
        the recorded exceptions; the grandfathering pass needs the raw set."""
        head_proj = _parse_project(source_path, language)
        annotated, has_diff, base_proj = _resolve_baseline_and_diff(
            head_proj=head_proj,
            cfg_language=language,
            config_dir=config_dir,
            explicit_reference=reference,
            explicit_base_ref=base_ref,
            repo_path=repo,
            default_reference=cfg.reference,
        )
        return run_checks(
            annotated,
            loaded.rules,
            has_diff=has_diff,
            baseline=load_baseline(config_dir) if filtered else None,
            baseline_project=base_proj,
            source_context=ctx_info,
            bypass_locks=bypass_locks,
            bypass_reason=bypass_reason,
        )

    if accept:
        _apply_automatic_exceptions(accept, loaded, ctx_info, config_dir, run, force=force)
        return

    report = run(filtered=True)

    human_text = report.to_human()
    if format == "human":
        typer.echo(human_text, nl=False)
    else:
        import json as _json

        typer.echo(_json.dumps(report.to_json(), indent=2, sort_keys=True))

    json_target = json_out or cfg.json_out
    if json_target is not None:
        report.write_json(json_target)
        typer.echo(f"wrote {json_target}")

    # The human report is what `cdec exceptions patch` expects to be handed
    # back, marked up — so the log is that text verbatim, whatever --format said.
    log_target = log_out or cfg.log_out
    if log_target is not None:
        log_target.parent.mkdir(parents=True, exist_ok=True)
        log_target.write_text(human_text, encoding="utf-8")
        typer.echo(f"wrote {log_target}")

    if report.has_failures(fail_on_sev):
        raise typer.Exit(code=1)


def _parse_auto_accept(values: list[str]) -> set[str]:
    """Normalise `--automatic-exceptions` into the set of things to accept."""
    out: set[str] = set()
    for raw in values:
        for part in str(raw).split(","):
            item = part.strip().lower()
            if not item:
                continue
            if item not in AUTO_ACCEPT_CHOICES:
                raise typer.BadParameter(
                    f"--automatic-exceptions must be one of "
                    f"{', '.join(AUTO_ACCEPT_CHOICES)}; got {item!r}"
                )
            out.add(item)
    if "all" in out:
        out = {"rules", "locks", "reference"}
    return out


def _apply_automatic_exceptions(
    accept: set[str],
    loaded: "LoadedRules",
    ctx_info: "SourceContext",
    config_dir: Path,
    run: "Callable[..., Report]",
    *,
    force: bool,
) -> None:
    """Record the current state as approved, instead of failing on it.

    Order matters. The rules that carry a baseline of their own (the reference
    snapshot, the lock ledger) are settled first, then the checks are re-run,
    and only what is *still* reported gets grandfathered into `exceptions:`. Do
    it the other way round and you would write exceptions for issues the
    re-snapshot was about to erase.
    """
    from code_constraints.lint.rules.base import RuleSkipped

    ordered = (
        ("reference", "reference-architecture"),
        ("locks", "implementation-locks"),
    )
    for what, type_name in ordered:
        if what not in accept:
            continue
        rules = loaded.of_type(type_name)
        if not rules:
            typer.echo(
                f"--automatic-exceptions {what}: no `{type_name}` rule in rules.yaml, "
                f"nothing to record."
            )
            continue
        for rule in rules:
            typer.echo(f"[{rule.rule_id}] recording the current state:")
            try:
                lines = rule.accept_current_state(_auto_accept_context(ctx_info), force=force)
            except RuleSkipped as exc:
                typer.echo(f"  skipped: {exc}")
                continue
            for line in lines:
                typer.echo(line)

    if "rules" in accept:
        report = run(filtered=False)
        grandfathered = [v for v in report.violations if v.waivable]
        path = write_baseline(config_dir, grandfathered)
        typer.echo(
            f"--automatic-exceptions rules: recorded {len(grandfathered)} exception(s) "
            f"in {path}"
        )
        refused = [v for v in report.violations if not v.waivable]
        if refused:
            typer.echo(
                f"  {len(refused)} lock violation(s) were NOT grandfathered — a frozen "
                f"implementation is accepted with "
                f"`--automatic-exceptions locks --force`, never as an exception:"
            )
            for v in refused:
                typer.echo(f"    - [{v.key()}] {v.qualified_name}")


def _auto_accept_context(source_context: "SourceContext") -> "RuleContext":
    """A minimal `RuleContext` for `accept_current_state`.

    The baselining hooks re-read the source themselves and never look at the
    model, so there is no reason to parse one just to hand it over.
    """
    from code_constraints.core.model import Project
    from code_constraints.lint.rules.base import RuleContext

    language = cast(SourceLanguage, source_context.language or "python")
    return RuleContext(
        project=Project(source_language=language),
        has_diff=False,
        source=source_context.source,
        language=source_context.language,
        config_dir=source_context.config_dir,
        reference_path=source_context.reference_path,
    )


def _warn_about_legacy_files(config_dir: Path) -> None:
    """Point out per-concern files that `rules.yaml` has superseded."""
    from code_constraints.lint.config import legacy_files

    stale = legacy_files(config_dir)
    if not stale:
        return
    names = ", ".join(p.name for p in stale)
    typer.echo(
        f"note: {names} in {config_dir} are the old per-concern files. They are still "
        f"read, but everything now lives in rules.yaml — fold them in with "
        f"`cdec init --migrate`.",
        err=True,
    )


# ---------------------------------------------------------------------------
# Retired commands.
#
# `enforce`, `lock` and `reference test` were three more gates with three more
# reports and three more exit codes. They are rule types in `rules.yaml` now and
# run inside `cdec check`. Typer would answer an old invocation with "No such
# command", which tells a user nothing, so each one survives as a hidden stub
# that says where the behaviour went.
# ---------------------------------------------------------------------------

_RETIRED = {
    "enforce": (
        "`cdec enforce` is now the `tag-conformance` rule type, checked by "
        "`cdec check`.\n"
        "Add this to .cdec/rules.yaml:\n"
        "    - id: tags-must-be-honoured\n"
        "      type: tag-conformance\n"
        "      severity: error\n"
        "then run `cdec check`."
    ),
    "lock": (
        "`cdec lock` is now the `implementation-locks` rule type, checked by "
        "`cdec check`.\n"
        "Add this to .cdec/rules.yaml:\n"
        "    - id: frozen-implementations\n"
        "      type: implementation-locks\n"
        "      severity: error\n"
        "then:\n"
        "    cdec check                                       # verify (was: lock check)\n"
        "    cdec check --automatic-exceptions locks          # baseline (was: lock set)\n"
        "    cdec check --automatic-exceptions locks --force  # re-baseline (was: --force)\n"
        "The ledger lives in the `locks:` section of rules.yaml; "
        "`cdec init --migrate` folds an existing .cdec/locks.yaml in."
    ),
}


def _retired(name: str) -> None:
    typer.echo(_RETIRED[name], err=True)
    raise typer.Exit(code=2)


_PASSTHROUGH = {"ignore_unknown_options": True, "allow_extra_args": True}


@app.command(hidden=True, context_settings=_PASSTHROUGH)
def enforce(ctx: typer.Context) -> None:
    """Retired — see `cdec check` and the `tag-conformance` rule type."""
    _retired("enforce")


@app.command(hidden=True, context_settings=_PASSTHROUGH)
def lock(ctx: typer.Context) -> None:
    """Retired — see `cdec check` and the `implementation-locks` rule type."""
    _retired("lock")


# ---------------------------------------------------------------------------
# `cdec exceptions` — the review loop.
#
# Enforcement that can only say "no" gets switched off. These commands are the
# other half: read the report, decide which issues are acceptable, record the
# decision (with a reason) in the `exceptions:` section of `.cdec/rules.yaml`,
# and keep moving. Every issue prints a stable key, so a decision can be quoted
# by a human editing a text file or by an agent passing a key on the command
# line — the two paths resolve to exactly the same operation.
# ---------------------------------------------------------------------------

exceptions_app = typer.Typer(
    help=(
        "Accept known violations, with a reason. `review` writes an editable "
        "report, `patch` applies the lines you marked [ALLOW], `allow`/`remove` "
        "take keys directly, `prune` drops the ones that no longer apply."
    )
)
app.add_typer(exceptions_app, name="exceptions")
# `baseline` was the old name for this group, back when the decisions lived in
# their own file. Kept as a hidden alias so existing scripts and muscle memory
# keep working.
app.add_typer(exceptions_app, name="baseline", hidden=True)


@exceptions_app.command("review")
def exceptions_review(
    config_dir: Path = typer.Option(Path(".cdec"), "--config", help="`.cdec/` folder."),
    out: Optional[Path] = typer.Option(
        None, "--out", "-o", help="Write the review file here (default: stdout)."
    ),
    source: Optional[Path] = typer.Option(None, "--source", help="Override source tree."),
    reference: Optional[Path] = typer.Option(None, "--reference", help="Override the reference model."),
    base_ref: Optional[str] = typer.Option(None, "--base-ref", help="Git ref to use as baseline."),
    repo: Path = typer.Option(Path("."), "--repo", help="Git repo root (only used with --base-ref)."),
    include_waived: bool = typer.Option(
        False, "--all", help="Include already-accepted issues (mark them [REMOVE] to withdraw)."
    ),
    format: str = typer.Option("text", "--format", help="text | json"),
) -> None:
    """Write every current issue as one markable line per issue.

    Mark the ones you accept with `[ALLOW]` (optionally `[ALLOW: reason]`) and
    feed the file back through `cdec exceptions patch`.
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
                "skipped": [{"rule": r, "reason": reason} for r, reason in collected.skipped],
            },
            indent=2,
            sort_keys=True,
        )
        _write_or_echo(payload + "\n", out)
        return

    from code_constraints.waivers import render_review

    text = render_review(collected.issues, include_waived=include_waived)
    for rule_id, reason in collected.skipped:
        text += f"# skipped: {rule_id}: {reason}\n"
    _write_or_echo(text, out)


@exceptions_app.command("patch")
def exceptions_patch(
    file: Path = typer.Option(
        ..., "--file", "-f",
        help="Reviewed report. Use '-' to read from stdin.",
    ),
    config_dir: Path = typer.Option(Path(".cdec"), "--config", help="`.cdec/` folder."),
    reason: str = typer.Option(
        "", "--reason", help="Reason applied to lines that don't carry [ALLOW: …]."
    ),
    source: Optional[Path] = typer.Option(None, "--source", help="Override source tree."),
    reference: Optional[Path] = typer.Option(None, "--reference", help="Override the reference model."),
    base_ref: Optional[str] = typer.Option(None, "--base-ref", help="Git ref to use as baseline."),
    repo: Path = typer.Option(Path("."), "--repo", help="Git repo root (only used with --base-ref)."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Report what would change; write nothing."),
    ignore_unknown: bool = typer.Option(
        False, "--ignore-unknown",
        help="Don't fail on keys that match no current issue (e.g. a stale report).",
    ),
) -> None:
    """Apply the `[ALLOW]` / `[REMOVE]` marks in a reviewed report.

    Any text file works — the output of `cdec exceptions review`, of
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
    _report_apply(result, collected.ledger_path, dry_run=dry_run)
    if result.changed and not dry_run:
        save_waivers(config_dir, collected.store)
    _exit_on_apply_failure(result, ignore_unknown=ignore_unknown)


@exceptions_app.command("allow")
def exceptions_allow(
    keys: list[str] = typer.Argument(..., help="Issue keys, e.g. V-1A2B3C4D."),
    config_dir: Path = typer.Option(Path(".cdec"), "--config", help="`.cdec/` folder."),
    reason: str = typer.Option("", "--reason", help="Why this issue is acceptable."),
    source: Optional[Path] = typer.Option(None, "--source", help="Override source tree."),
    reference: Optional[Path] = typer.Option(None, "--reference", help="Override the reference model."),
    base_ref: Optional[str] = typer.Option(None, "--base-ref", help="Git ref to use as baseline."),
    repo: Path = typer.Option(Path("."), "--repo", help="Git repo root (only used with --base-ref)."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Report what would change; write nothing."),
) -> None:
    """Accept issues by key — the path an agent or a one-liner takes.

    The keys must name issues that are reported right now; a key that matches
    nothing is an error, not a silent no-op, because it almost always means the
    report being quoted is stale.
    """
    from code_constraints.waivers import allow_keys, save_waivers

    collected = _collect_issues_cli(
        config_dir, source=source, reference=reference, base_ref=base_ref, repo=repo
    )
    result = allow_keys(collected.store, collected, keys, reason=reason)
    _report_apply(result, collected.ledger_path, dry_run=dry_run)
    if result.changed and not dry_run:
        save_waivers(config_dir, collected.store)
    _exit_on_apply_failure(result)


@exceptions_app.command("remove")
def exceptions_remove(
    keys: list[str] = typer.Argument(..., help="Issue keys to stop allowing."),
    config_dir: Path = typer.Option(Path(".cdec"), "--config", help="`.cdec/` folder."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Report what would change; write nothing."),
) -> None:
    """Withdraw exceptions by key, so the issue blocks again.

    Needs no source parse: the ledger alone identifies what to drop, which
    means an exception can always be withdrawn even if the code no longer parses.
    """
    from code_constraints.waivers import remove_keys, save_waivers

    store = _load_waivers_cli(config_dir)
    result = remove_keys(store, keys)
    _report_apply(result, _ledger_path(config_dir), dry_run=dry_run)
    if result.changed and not dry_run:
        save_waivers(config_dir, store)
    if result.malformed or result.not_waived:
        raise typer.Exit(code=1)


@exceptions_app.command("list")
def exceptions_list(
    config_dir: Path = typer.Option(Path(".cdec"), "--config", help="`.cdec/` folder."),
    engine: Optional[str] = typer.Option(
        None, "--engine", help="Only show one engine's exceptions: check | enforce | reference."
    ),
    format: str = typer.Option("human", "--format", help="human | json"),
) -> None:
    """Show what is currently accepted, and why."""
    if format not in ("human", "json"):
        raise typer.BadParameter(f"unknown format: {format}")
    ledger = _ledger_path(config_dir)
    store = _load_waivers_cli(config_dir)
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
        typer.echo(f"no exceptions recorded in {ledger}.")
        return
    typer.echo(f"{len(waivers)} exception(s) in {ledger}:")
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


@exceptions_app.command("prune")
def exceptions_prune(
    config_dir: Path = typer.Option(Path(".cdec"), "--config", help="`.cdec/` folder."),
    source: Optional[Path] = typer.Option(None, "--source", help="Override source tree."),
    reference: Optional[Path] = typer.Option(None, "--reference", help="Override the reference model."),
    base_ref: Optional[str] = typer.Option(None, "--base-ref", help="Git ref to use as baseline."),
    repo: Path = typer.Option(Path("."), "--repo", help="Git repo root (only used with --base-ref)."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Report what would change; write nothing."),
) -> None:
    """Drop exceptions for issues that no longer occur.

    An exception outlives the code it was granted for, and a stale one silently
    pre-approves a future violation of the same rule on the same element. This
    only prunes engines that actually ran, so a skipped rule never looks like a
    clean one.
    """
    from code_constraints.waivers import prune as prune_waivers
    from code_constraints.waivers import save_waivers

    collected = _collect_issues_cli(
        config_dir, source=source, reference=reference, base_ref=base_ref, repo=repo
    )
    stale = prune_waivers(collected.store, collected)
    if not stale:
        typer.echo("no stale exceptions.")
        return
    verb = "would drop" if dry_run else "dropped"
    typer.echo(f"{verb} {len(stale)} stale exception(s):")
    for w in stale:
        detail = f" {w.detail}" if w.detail else ""
        typer.echo(f"  - [{w.key}] [{w.engine}/{w.rule}] {w.qualified_name}{detail}")
    if not dry_run:
        save_waivers(config_dir, collected.store)
        typer.echo(f"wrote {collected.ledger_path}")


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
    if chosen not in SUPPORTED_LANGUAGES:
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


reference_app = typer.Typer(
    help=(
        "Work with the architecture reference model. Testing the code against "
        "it is the `reference-architecture` rule type, run by `cdec check`; "
        "these commands author and visualise it."
    )
)
app.add_typer(reference_app, name="reference")


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
    """Lock an authored model in as the target architecture.

    Takes a hand-written / agent-written model file (JSON or XMI) and writes it
    to the project's reference model, so a `reference-architecture` rule starts
    constraining development against it immediately. This is the "accept the
    proposal" step of the propose -> review -> lock workflow.

    The other way to produce a reference is to snapshot the code as it stands:
    `cdec check --automatic-exceptions reference`. The distinction is the point.
    `set` declares what the code *should become*; the snapshot records what it
    *is*.
    """
    proj = _load_model_cli(model)
    if reference is not None:
        ref_path = reference
    else:
        try:
            cfg = load_project_config(config_dir)
            ref_path = cfg.reference_path
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
        help="Source tree to compare (falls back to the `source` in rules.yaml).",
    ),
    reference: Optional[Path] = typer.Option(
        None, "--reference", help="Reference model (default: .cdec/reference.xmi)."
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
    """Open the web viewer on a diff of the current code against the reference."""
    import uuid

    source_path, chosen_lang, ref_path = _resolve_reference_inputs(
        source, lang, reference, config_dir
    )
    if not ref_path.is_file():
        typer.echo(
            f"reference model not found: {ref_path}\n"
            f"Snapshot the current architecture with "
            f"`cdec check --automatic-exceptions reference`, or promote an authored "
            f"model with `cdec reference set <model>`.",
            err=True,
        )
        raise typer.Exit(code=2)

    reference_proj = _load_model_cli(ref_path)
    current = _parse_project(source_path, chosen_lang)
    try:
        # The reference is the *target* architecture and the codebase is the
        # *current* state, so the codebase is the old side and the reference the
        # new side: elements only in the reference render as green additions
        # ("the code still needs to grow this"), elements only in the code as
        # red removals. This is intentionally the inverse of `diff-vs-xmi` and of
        # the `reference-architecture` rule, where the reference is the old
        # baseline.
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


@reference_app.command("test", hidden=True, context_settings=_PASSTHROUGH)
def reference_test(ctx: typer.Context) -> None:
    """Retired — see `cdec check` and the `reference-architecture` rule type."""
    typer.echo(
        "`cdec reference test` is now the `reference-architecture` rule type, checked "
        "by `cdec check`.\n"
        "Add this to .cdec/rules.yaml:\n"
        "    - id: public-shape-is-frozen\n"
        "      type: reference-architecture\n"
        "      severity: error\n"
        "then run `cdec check`.",
        err=True,
    )
    raise typer.Exit(code=2)


@reference_app.command("update", hidden=True, context_settings=_PASSTHROUGH)
def reference_update(ctx: typer.Context) -> None:
    """Retired — see `cdec check --automatic-exceptions reference`."""
    typer.echo(
        "`cdec reference update` is now "
        "`cdec check --automatic-exceptions reference`, which re-snapshots "
        ".cdec/reference.xmi from the current source.",
        err=True,
    )
    raise typer.Exit(code=2)


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


# ---------- config helpers ----------

def _load_config_cli(config_dir: Path):
    """`load_project_config` with typer-friendly error reporting."""
    try:
        return load_project_config(config_dir)
    except ConfigError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc


def _split_csv(values: list[str]) -> list[str]:
    """Flatten a repeatable, comma-separated option into a list of names."""
    return [part.strip() for raw in values for part in str(raw).split(",") if part.strip()]


def _load_rules_cli(config_dir: Path, only: list[str] | None = None):
    """`load_rules` with typer-friendly error reporting."""
    try:
        return load_rules(config_dir, only)
    except ConfigError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc


def _ledger_path(config_dir: Path) -> Path:
    """The file exceptions are recorded in — `.cdec/rules.yaml`."""
    from code_constraints.waivers import ledger_paths

    return ledger_paths(config_dir)[0]


# ---------- review helpers ----------

def _collect_issues_cli(
    config_dir: Path,
    *,
    source: Optional[Path] = None,
    reference: Optional[Path] = None,
    base_ref: Optional[str] = None,
    repo: Path = Path("."),
) -> "Collected":
    """Run every rule and return the keyed issue list, with typer-friendly
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


def _load_waivers_cli(config_dir: Path) -> "WaiverStore":
    from code_constraints.waivers import load_waivers
    from code_constraints.waivers.store import WaiverFileError

    try:
        return load_waivers(config_dir)
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
        "ruleId": issue.rule_id,
        "qualifiedName": issue.qualified_name,
        "detail": issue.detail,
        "message": issue.message,
        "severity": issue.severity,
        "file": issue.file,
        "line": issue.line,
        "waived": issue.waived,
        "waivable": issue.waivable,
    }


def _report_apply(result: "ApplyResult", ledger_path: Path, *, dry_run: bool) -> None:
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
        typer.echo("no changes to the exceptions list.")
    elif dry_run:
        typer.echo(f"dry run — {ledger_path} not written.")
    else:
        typer.echo(f"wrote {ledger_path}")


def _exit_on_apply_failure(result: "ApplyResult", *, ignore_unknown: bool = False) -> None:
    failed = bool(result.refused or result.malformed or result.problems)
    if result.unknown and not ignore_unknown:
        failed = True
    if failed:
        raise typer.Exit(code=1)


def _resolve_reference_inputs(
    source: Optional[Path],
    lang: Optional[str],
    reference: Optional[Path],
    config_dir: Path,
) -> tuple[Path, str, Path]:
    """Resolve (source_path, language, reference_path) from explicit args with a
    `.cdec/` fallback. Explicit args always win; `.cdec/rules.yaml` fills the gaps
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
            "no source given and none found in .cdec/rules.yaml; pass a SOURCE "
            "argument or run from a scaffolded project (cdec init)."
        )

    chosen_lang = lang or (cfg.language if cfg else None) or detect_language(source_path)
    if chosen_lang is None:
        raise typer.BadParameter(
            f"could not determine a language for {source_path}; pass --lang explicitly."
        )
    if chosen_lang not in SUPPORTED_LANGUAGES:
        raise typer.BadParameter(f"unsupported language: {chosen_lang}")

    if reference is not None:
        ref_path = reference
    elif cfg is not None:
        ref_path = cfg.reference_path
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
