"""Tests for the dependency-fingerprint stamps that gate the install steps."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from code_constraints.cli import depstamp


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_fingerprint_is_stable_and_order_independent(tmp_path):
    a = _write(tmp_path / "a.txt", "alpha")
    b = _write(tmp_path / "b.txt", "beta")

    first = depstamp.fingerprint([a, b])
    assert first == depstamp.fingerprint([a, b])  # stable across calls
    assert first == depstamp.fingerprint([b, a])  # independent of arg order


def test_fingerprint_changes_on_content_change(tmp_path):
    f = _write(tmp_path / "a.txt", "v1")
    before = depstamp.fingerprint([f])
    _write(tmp_path / "a.txt", "v2")
    assert depstamp.fingerprint([f]) != before


def test_directory_input_tracks_added_and_removed_files(tmp_path):
    src = tmp_path / "src"
    _write(src / "one.txt", "1")
    base = depstamp.fingerprint([src])

    added = _write(src / "two.txt", "2")
    assert depstamp.fingerprint([src]) != base

    added.unlink()
    assert depstamp.fingerprint([src]) == base  # back to original set


def test_is_changed_and_write_stamp_roundtrip(tmp_path):
    f = _write(tmp_path / "pyproject.toml", "deps")
    stamp = tmp_path / ".venv" / ".cdec-stamp-python"

    assert depstamp.is_changed(stamp, [f])  # missing stamp -> changed
    depstamp.write_stamp(stamp, [f])
    assert not depstamp.is_changed(stamp, [f])  # matches after write

    _write(tmp_path / "pyproject.toml", "deps2")
    assert depstamp.is_changed(stamp, [f])  # content drift -> changed


def test_base_makes_hash_location_independent(tmp_path):
    repo1 = tmp_path / "repo1"
    repo2 = tmp_path / "repo2"
    f1 = _write(repo1 / "pyproject.toml", "same")
    f2 = _write(repo2 / "pyproject.toml", "same")

    assert depstamp.fingerprint([f1], base=repo1) == depstamp.fingerprint([f2], base=repo2)


def test_cli_check_exit_codes(tmp_path):
    f = _write(tmp_path / "a.txt", "x")
    stamp = tmp_path / "s.stamp"
    script = Path(depstamp.__file__)

    def run(cmd):
        return subprocess.run(
            [sys.executable, str(script), cmd, "--stamp", str(stamp), str(f)]
        ).returncode

    assert run("check") == 0  # no stamp -> changed (run the step)
    assert run("write") == 0
    assert run("check") == 1  # stamp matches -> unchanged (skip)
