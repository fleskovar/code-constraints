"""Tests for `cdec update` repo-root detection (the part that's safe to test
without touching git/pip/npm)."""

from __future__ import annotations

from pathlib import Path

import pytest

from code_constraints.cli.update import UpdateError, find_repo_root


def test_find_repo_root_locates_checkout(tmp_path):
    """A directory with both .git and pyproject.toml is the checkout root."""
    root = tmp_path / "repo"
    (root / "src" / "code_constraints" / "cli").mkdir(parents=True)
    (root / ".git").mkdir()
    (root / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    start = root / "src" / "code_constraints" / "cli" / "update.py"

    assert find_repo_root(start) == root.resolve()


def test_find_repo_root_errors_outside_checkout(tmp_path):
    """No .git/pyproject.toml above the start path -> a helpful UpdateError."""
    start = tmp_path / "nowhere" / "deep" / "file.py"
    start.parent.mkdir(parents=True)

    with pytest.raises(UpdateError):
        find_repo_root(start)
