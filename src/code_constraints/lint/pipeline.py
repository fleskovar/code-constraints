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
