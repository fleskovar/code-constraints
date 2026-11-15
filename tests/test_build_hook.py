"""The build hook puts the web UI into every package, or fails the build.

A wheel built from a git checkout used to have no UI, because `frontend/dist`
is gitignored, and `cdec ui` then served a JSON placeholder. The real npm build
runs in CI (`.github/actions/build-dist` and `verify_dist.py`); these tests
cover the decisions that do not need npm.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("hatch_build", ROOT / "hatch_build.py")
assert _spec is not None and _spec.loader is not None
hatch_build = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hatch_build)

STATIC = hatch_build.STATIC


def _quiet(*_args: object) -> None:
    pass


def _tree(root: Path, *files: str) -> Path:
    for name in files:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(name, encoding="utf-8")
    return root


def test_a_checkout_with_no_npm_and_no_build_fails(tmp_path: Path) -> None:
    root = _tree(tmp_path, "frontend/package.json")
    with pytest.raises(hatch_build.UIBuildError, match="Node.js"):
        hatch_build.prepare_ui(root, None, _quiet)
    assert not (root / STATIC).exists()


def test_a_tree_with_no_ui_and_no_frontend_fails(tmp_path: Path) -> None:
    with pytest.raises(hatch_build.UIBuildError, match="CDEC_SKIP_UI_BUILD"):
        hatch_build.prepare_ui(tmp_path, "npm", _quiet)


def test_an_existing_build_is_copied_when_npm_is_missing(tmp_path: Path) -> None:
    root = _tree(
        tmp_path,
        "frontend/package.json",
        "frontend/dist/index.html",
        "frontend/dist/assets/app.js",
        f"{STATIC.as_posix()}/assets/old.js",
    )
    static = hatch_build.prepare_ui(root, None, _quiet)
    assert sorted(p.relative_to(static).as_posix() for p in static.rglob("*.*")) == [
        "assets/app.js",
        "index.html",
    ]


def test_an_unpacked_sdist_keeps_its_ui_and_does_not_build(tmp_path: Path) -> None:
    # `python -m build` makes the wheel from the sdist, in a folder with no
    # node_modules. The sdist carries the UI that the hook built.
    root = _tree(
        tmp_path, "PKG-INFO", "frontend/package.json", f"{STATIC.as_posix()}/index.html"
    )
    assert hatch_build.prepare_ui(root, "no-such-npm", _quiet) == root / STATIC


def test_the_hook_is_registered_and_the_ui_ships() -> None:
    import tomllib

    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    build = config["tool"]["hatch"]["build"]
    assert "custom" in build["hooks"]
    assert f"{STATIC.as_posix()}/**" in build["artifacts"]


def test_an_install_with_no_ui_explains_the_fix(monkeypatch: pytest.MonkeyPatch) -> None:
    """With no bundle anywhere, `/` is a help page, not the app and not JSON."""
    import importlib

    from fastapi.testclient import TestClient

    import code_constraints.web.app as web_app

    real_exists = Path.exists
    monkeypatch.setattr(
        Path, "exists", lambda p: False if p.name in ("dist", "_static") else real_exists(p)
    )
    try:
        reloaded = importlib.reload(web_app)
        assert reloaded._frontend_dist is None
        page = TestClient(reloaded.app).get("/")
        assert page.status_code == 200 and "text/html" in page.headers["content-type"]
        assert "pip install --upgrade --force-reinstall code-constraints" in page.text
        assert "npm run build" in page.text
    finally:
        monkeypatch.undo()
        importlib.reload(web_app)
