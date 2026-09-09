"""`cdec update` — self-update the installation in place.

Equivalent to re-running the standalone installer (`install/install.{sh,ps1}`):
pull the latest code from GitHub, re-sync Python dependencies (picking up any
requirement changes), and rebuild the web frontend. Operates on the git checkout
that this CLI is running from, using the same virtualenv (`sys.executable`).

The refreshed code takes effect on the next `cdec` invocation — the currently
running process keeps the modules it already imported.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from code_constraints.cli import depstamp


class UpdateError(Exception):
    """Raised when the update cannot proceed (not a checkout, missing tool, …)."""


def find_repo_root(start: Path | None = None) -> Path:
    """Walk up from this module to the git checkout that contains the project.

    Looks for a directory holding both ``.git`` and ``pyproject.toml`` — that's
    the editable checkout the installer manages (``$CDEC_HOME/repo``) or a
    developer clone.
    """
    here = (start or Path(__file__)).resolve()
    for candidate in here.parents:
        if (candidate / ".git").exists() and (candidate / "pyproject.toml").is_file():
            return candidate
    raise UpdateError(
        "could not locate the code-constraints git checkout to update.\n"
        "This command updates an installation created by the standalone installer "
        "(or a git clone). If you installed code-constraints some other way, update it "
        "the same way you installed it (e.g. `pip install -U code-constraints`)."
    )


def _current_branch(repo_root: Path, git: str) -> str:
    out = subprocess.run(
        [git, "-C", str(repo_root), "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.strip()


def _run(cmd: list[str], *, cwd: Path, step: str) -> None:
    """Run a child process, streaming its output. Raise UpdateError on failure."""
    result = subprocess.run(cmd, cwd=str(cwd), check=False)
    if result.returncode != 0:
        raise UpdateError(f"{step} failed (exit {result.returncode}): {' '.join(cmd)}")


def _build_inputs(frontend_dir: Path) -> list[Path]:
    """Files whose change should trigger a frontend rebuild (source + configs)."""
    candidates = [
        frontend_dir / "src",
        frontend_dir / "package.json",
        frontend_dir / "package-lock.json",
        frontend_dir / "vite.config.ts",
        frontend_dir / "svelte.config.js",
        frontend_dir / "tsconfig.json",
        frontend_dir / "tsconfig.app.json",
        frontend_dir / "tsconfig.node.json",
        frontend_dir / "index.html",
    ]
    return [p for p in candidates if p.exists()]


def run_update(
    *,
    branch: str | None = None,
    frontend: bool = True,
    force: bool = False,
    echo=print,
) -> Path:
    """Perform the in-place update. Returns the repo root that was updated.

    Mirrors the installer flow: ``git fetch`` + ``pull --ff-only`` → ``pip
    install -e ".[dev]"`` (via the running interpreter) → ``npm install`` +
    ``npm run build``.

    The three install steps are fingerprinted (see :mod:`code_constraints.cli.depstamp`): a
    step is skipped when its inputs are unchanged since the last successful run,
    unless ``force`` is set. The git pull always runs — it's cheap and it's what
    produces the changes the fingerprints then detect.
    """
    repo_root = find_repo_root()

    git = shutil.which("git")
    if git is None:
        raise UpdateError("git is not installed or not on PATH.")

    target_branch = branch or _current_branch(repo_root, git)

    # 1. Pull latest code.
    echo(f"==> Updating source ({target_branch}) in {repo_root}")
    _run([git, "-C", str(repo_root), "fetch", "--prune", "origin", target_branch],
         cwd=repo_root, step="git fetch")
    _run([git, "-C", str(repo_root), "checkout", target_branch],
         cwd=repo_root, step="git checkout")
    _run([git, "-C", str(repo_root), "pull", "--ff-only", "origin", target_branch],
         cwd=repo_root, step="git pull")

    # 2. Re-sync Python dependencies using the venv this CLI runs from. Skip when
    #    pyproject.toml is unchanged — the editable install already reflects any
    #    source edits, so only a dependency change warrants a reinstall.
    venv_dir = Path(sys.executable).resolve().parent.parent
    py_stamp = venv_dir / ".cdec-stamp-python"
    py_inputs = [repo_root / "pyproject.toml"]
    if force or depstamp.is_changed(py_stamp, py_inputs, base=repo_root):
        echo("==> Installing / updating Python dependencies")
        _run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"],
             cwd=repo_root, step="pip upgrade")
        _run([sys.executable, "-m", "pip", "install", "-e", ".[dev]"],
             cwd=repo_root, step="pip install")
        depstamp.write_stamp(py_stamp, py_inputs, base=repo_root)
    else:
        echo("==> Python dependencies unchanged — skipping pip install")

    # 3. Rebuild the frontend.
    if frontend:
        frontend_dir = repo_root / "frontend"
        npm = shutil.which("npm")
        if npm is None:
            echo("WARNING: npm not found on PATH — skipping frontend rebuild. "
                 "The web UI may be stale until you build it (Node 20+ required).")
        elif not frontend_dir.is_dir():
            echo(f"WARNING: {frontend_dir} not found — skipping frontend rebuild.")
        else:
            deps_stamp = frontend_dir / "node_modules" / ".cdec-stamp-deps"
            deps_inputs = [frontend_dir / "package.json", frontend_dir / "package-lock.json"]
            if force or depstamp.is_changed(deps_stamp, deps_inputs, base=repo_root):
                echo("==> Installing frontend dependencies")
                _run([npm, "install"], cwd=frontend_dir, step="npm install")
                depstamp.write_stamp(deps_stamp, deps_inputs, base=repo_root)
            else:
                echo("==> Frontend dependencies unchanged — skipping npm install")

            build_stamp = frontend_dir / "dist" / ".cdec-stamp-build"
            build_inputs = _build_inputs(frontend_dir)
            if force or depstamp.is_changed(build_stamp, build_inputs, base=repo_root):
                echo("==> Rebuilding the web UI")
                _run([npm, "run", "build"], cwd=frontend_dir, step="npm run build")
                depstamp.write_stamp(build_stamp, build_inputs, base=repo_root)
            else:
                echo("==> Frontend sources unchanged — skipping npm run build")

    return repo_root
