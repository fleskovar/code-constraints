"""Parse the source and resolve the baseline — the front half of `cdec check`.

Extracted so that anything needing the *same* issues `cdec check` would report
computes them the same way. That matters for the review workflow: a key is only
useful if the command that grants a waiver sees exactly the issues the command
that printed the report saw, which means resolving the baseline identically
(same reference file, same `--base-ref`, same diff).

Pure functions raising `PipelineError`; the CLI adapts to typer, other callers
adapt as they like.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any

from code_constraints.core.diff import diff_projects
from code_constraints.core.model import SUPPORTED_LANGUAGES, Project
from code_constraints.lint.config import REFERENCE_FILENAME

SUPPORTED_LANGS = SUPPORTED_LANGUAGES


class PipelineError(RuntimeError):
    """Raised when the source or the baseline can't be prepared."""


def parse_source(path: Path, lang: str) -> Project:
    if lang == "python":
        from code_constraints.python import parse_project
    elif lang == "csharp":
        from code_constraints.csharp import parse_project
    elif lang == "typescript":
        from code_constraints.typescript import parse_project
    elif lang == "svelte":
        from code_constraints.svelte import parse_project
    elif lang == "odin":
        from code_constraints.odin import parse_project
    elif lang == "lua":
        from code_constraints.lua import parse_project
    elif lang == "julia":
        from code_constraints.julia import parse_project
    else:
        raise PipelineError(f"unsupported language: {lang}")
    return parse_project(path)


def snapshot_reference(source: Path, lang: str, reference_path: Path) -> Project:
    """Write the model of the current source to the reference file.

    The reference is the baseline of every `scope: diff` rule, so a project
    re-snapshots it with or without a `reference-architecture` rule.
    """
    from code_constraints.core.model_io import save_model

    project = parse_source(source, lang)
    reference_path.parent.mkdir(parents=True, exist_ok=True)
    save_model(project, reference_path)
    return project


def checkout_revision(repo: Any, ref: str, dest: Path) -> Path:
    """Copy the tree at `ref` into `dest` (avoids touching the working tree)."""
    dest.mkdir(parents=True, exist_ok=True)
    commit = repo.commit(ref)
    archive = dest.with_suffix(".tar")
    with archive.open("wb") as fh:
        repo.archive(fh, treeish=commit.hexsha, format="tar")
    shutil.unpack_archive(str(archive), str(dest), format="tar")
    archive.unlink()
    return dest


def resolve_baseline(
    *,
    head_proj: Project,
    lang: str,
    config_dir: Path,
    explicit_reference: Path | None = None,
    explicit_base_ref: str | None = None,
    repo_path: Path = Path("."),
    default_reference: Path | None = None,
) -> tuple[Project, bool, Project | None]:
    """Returns (project_for_rules, has_diff, baseline_project).

    When no baseline is available, returns the head project unchanged with
    has_diff=False and a None baseline, so diff-scope rules get skipped rather
    than silently passing.
    """
    if explicit_base_ref:
        from git import Repo

        git_repo = Repo(str(Path(repo_path).resolve()))
        with tempfile.TemporaryDirectory(prefix="cdec-check-") as tmp:
            base_dir = checkout_revision(git_repo, explicit_base_ref, Path(tmp) / "base")
            base_proj = parse_source(base_dir, lang)
            try:
                annotated = diff_projects(base_proj, head_proj)
            except ValueError as exc:
                raise PipelineError(str(exc)) from exc
        return annotated, True, base_proj

    ref_path: Path | None = explicit_reference or default_reference
    if ref_path is None:
        candidate = config_dir / REFERENCE_FILENAME
        if candidate.is_file():
            ref_path = candidate

    if ref_path and ref_path.is_file():
        from code_constraints.core.model_io import load_model

        base_proj = load_model(ref_path)
        try:
            annotated = diff_projects(base_proj, head_proj)
        except ValueError as exc:
            raise PipelineError(str(exc)) from exc
        return annotated, True, base_proj

    return head_proj, False, None


def run_check(
    head_proj: Project,
    rules: Any,
    cfg: Any,
    *,
    source: Path | None,
    language: str,
    reference: Path | None = None,
    base_ref: str | None = None,
    repo: Path = Path("."),
    filtered: bool = True,
    bypass_locks: bool = False,
    bypass_reason: str = "",
) -> Any:
    """The back half of `cdec check`: resolve the baseline and run the rules.

    `head_proj` is the parsed source, or a model in its place. `cfg` is the
    `ProjectConfig`. `source` is None for a model: the rules that read source
    code then skip. `filtered` applies the exceptions; the grandfathering pass
    of `--automatic-exceptions rules` needs the raw set. The CLI and the web app
    both call this, so the two reports are one report.
    """
    from code_constraints.lint.baseline import load_baseline
    from code_constraints.lint.engine import SourceContext, run_checks

    annotated, has_diff, base_proj = resolve_baseline(
        head_proj=head_proj,
        lang=language,
        config_dir=cfg.config_dir,
        explicit_reference=reference,
        explicit_base_ref=base_ref,
        repo_path=repo,
        default_reference=cfg.reference,
    )
    return run_checks(
        annotated,
        rules,
        has_diff=has_diff,
        baseline=load_baseline(cfg.config_dir) if filtered else None,
        baseline_project=base_proj,
        source_context=SourceContext(
            source=source,
            language=language,
            config_dir=cfg.config_dir,
            reference_path=reference or cfg.reference_path,
        ),
        bypass_locks=bypass_locks,
        bypass_reason=bypass_reason,
    )
