"""Put the built web UI into the package on every build.

The UI is built into `frontend/dist`, which is generated and gitignored. Before
this hook, only `make dist` and the release workflow copied it into the
package, so a wheel built any other way (`pip install .`, `pip install
git+https://…`, `uv tool install` from a clone) had no UI. Its `cdec ui`
answered with a JSON placeholder. Now the build itself builds the UI and copies
it to `src/code_constraints/web/_static`, which `[tool.hatch.build] artifacts`
ships. It fails when it cannot, because an install with no UI is a broken
install that looks like a working one.

An editable install (`pip install -e .`) is skipped: the server serves
`frontend/dist` straight from the checkout.

`CDEC_SKIP_UI_BUILD=1` builds a package with the API only, on purpose.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

SKIP_ENV = "CDEC_SKIP_UI_BUILD"
STATIC = Path("src") / "code_constraints" / "web" / "_static"


class UIBuildError(RuntimeError):
    """The web UI cannot be built and is not in the source tree."""


def prepare_ui(root: Path, npm: str | None, log: Any = print) -> Path:
    """Make `src/code_constraints/web/_static` hold the built UI, and return it.

    `npm` is the npm executable, or None when it is not installed.
    """
    static = root / STATIC
    frontend = root / "frontend"
    # An unpacked sdist: this hook built the UI when it made the sdist, from the
    # sources in it. `python -m build` makes the wheel this way, in a temporary
    # folder with no node_modules, so building again would only cost a download.
    if (root / "PKG-INFO").is_file() and (static / "index.html").is_file():
        log("cdec: using the web UI of the source distribution")
        return static
    if not (frontend / "package.json").is_file():
        raise UIBuildError(
            f"there is no web UI in {static} and no frontend/ to build it from. "
            f"Set {SKIP_ENV}=1 to build a package with the API only."
        )
    if npm is not None:
        if not (frontend / "node_modules").is_dir():
            log("cdec: installing the frontend dependencies (npm ci)")
            _run([npm, "ci"], frontend)
        log("cdec: building the web UI (npm run build)")
        _run([npm, "run", "build"], frontend)
    elif (frontend / "dist" / "index.html").is_file():
        log("cdec: npm is not installed; using the existing frontend/dist, which can be old")
    else:
        raise UIBuildError(
            "cdec needs Node.js and npm to build its web UI from a source checkout, and npm "
            "is not on PATH. Install Node.js 20 or newer (https://nodejs.org) and build "
            "again, or install the released package: pip install code-constraints. Set "
            f"{SKIP_ENV}=1 to build a package with the API only."
        )
    dist = frontend / "dist"
    if not (dist / "index.html").is_file():
        raise UIBuildError(f"the frontend build wrote no {dist / 'index.html'}")
    shutil.rmtree(static, ignore_errors=True)
    shutil.copytree(dist, static)
    log(f"cdec: web UI copied to {static}")
    return static


def _run(cmd: list[str], cwd: Path) -> None:
    try:
        subprocess.run(cmd, cwd=cwd, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        shown = " ".join([Path(cmd[0]).stem, *cmd[1:]])
        raise UIBuildError(f"`{shown}` failed in {cwd}: {exc}") from exc


class CustomBuildHook(BuildHookInterface):  # type: ignore[type-arg]
    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        if self.target_name == "wheel" and version == "editable":
            return
        if os.environ.get(SKIP_ENV) == "1":
            self.app.display_warning(
                f"{SKIP_ENV}=1: this package has no web UI. `cdec ui` serves the API only."
            )
            return
        try:
            prepare_ui(Path(self.root), shutil.which("npm"), self.app.display_info)
        except UIBuildError as exc:
            self.app.abort(str(exc))
