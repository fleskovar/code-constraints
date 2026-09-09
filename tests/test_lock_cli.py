"""End-to-end CLI tests for `cdec lock` and its `cdec check` integration."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from code_constraints.cli.__main__ import app

PY_SHIM = '''
def locked(*args, **kwargs):
    if len(args) == 1 and not kwargs and callable(args[0]):
        return args[0]
    return lambda obj: obj
'''

BILLING = '''\
from cdec_rules import locked


class Invoice:
    @locked(reason="agreed settlement order")
    def settle(self, amount):
        tax = amount * 0.2
        return amount + tax

    def describe(self):
        return "invoice"
'''

CONFIG = """\
language: python
source: src_tree
baseline:
  reference: .cdec/reference.xmi
"""


def _run(args, cwd=None):
    runner = CliRunner()
    if cwd is None:
        return runner.invoke(app, args)
    here = os.getcwd()
    try:
        os.chdir(cwd)
        return runner.invoke(app, args)
    finally:
        os.chdir(here)


@pytest.fixture()
def project_dir(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    src = root / "src_tree"
    src.mkdir(parents=True)
    (src / "cdec_rules.py").write_text(PY_SHIM, encoding="utf-8")
    (src / "billing.py").write_text(BILLING, encoding="utf-8")
    uml = root / ".cdec"
    uml.mkdir()
    (uml / "config.yaml").write_text(CONFIG, encoding="utf-8")
    (uml / "rules.yaml").write_text("rules: []\n", encoding="utf-8")
    (uml / "baseline.yaml").write_text("violations: {}\n", encoding="utf-8")
    return root


def _edit(project_dir: Path, old: str, new: str) -> None:
    path = project_dir / "src_tree" / "billing.py"
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new), encoding="utf-8")


def _lockfile(project_dir: Path) -> dict:
    with (project_dir / ".cdec" / "locks.yaml").open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


# ---------- cdec lock set / check ----------

def test_lock_set_writes_the_ledger(project_dir):
    result = _run(["lock", "set"], cwd=project_dir)
    assert result.exit_code == 0, result.output
    assert "+ locked   Invoice.settle" in result.output

    data = _lockfile(project_dir)
    assert data["version"] == 1
    assert [e["target"] for e in data["locks"]] == ["Invoice.settle"]
    assert data["locks"][0]["reason"] == "agreed settlement order"


def test_lock_check_passes_on_a_clean_tree(project_dir):
    _run(["lock", "set"], cwd=project_dir)
    result = _run(["lock", "check"], cwd=project_dir)
    assert result.exit_code == 0, result.output
    assert "1 locked element(s) verified" in result.output


def test_lock_check_fails_on_a_changed_body(project_dir):
    _run(["lock", "set"], cwd=project_dir)
    _edit(project_dir, "amount * 0.2", "amount * 0.3")

    result = _run(["lock", "check"], cwd=project_dir)
    assert result.exit_code == 1
    assert "[changed]" in result.output
    assert "Invoice.settle" in result.output
    assert "cdec lock set --target Invoice.settle --force" in result.output


def test_lock_check_json_report(project_dir, tmp_path):
    _run(["lock", "set"], cwd=project_dir)
    _edit(project_dir, "amount * 0.2", "amount * 0.3")

    out = project_dir / "locks.json"
    result = _run(
        ["lock", "check", "--format", "json", "--json-out", str(out)], cwd=project_dir
    )
    assert result.exit_code == 1
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["summary"]["violations"] == 1
    assert payload["violations"][0]["kind"] == "changed"
    assert payload["violations"][0]["target"] == "Invoice.settle"


def test_lock_set_blocks_rebaseline_without_force(project_dir):
    _run(["lock", "set"], cwd=project_dir)
    before = _lockfile(project_dir)["locks"][0]["digest"]
    _edit(project_dir, "amount * 0.2", "amount * 0.3")

    result = _run(["lock", "set"], cwd=project_dir)
    assert result.exit_code == 1
    assert "have CHANGED and were left untouched" in result.output
    assert _lockfile(project_dir)["locks"][0]["digest"] == before


def test_lock_set_force_rebaselines(project_dir):
    _run(["lock", "set"], cwd=project_dir)
    before = _lockfile(project_dir)["locks"][0]["digest"]
    _edit(project_dir, "amount * 0.2", "amount * 0.3")

    result = _run(
        ["lock", "set", "--force", "--reason", "rate approved", "--owner", "lead"],
        cwd=project_dir,
    )
    assert result.exit_code == 0, result.output
    assert "~ rebased  Invoice.settle" in result.output

    entry = _lockfile(project_dir)["locks"][0]
    assert entry["digest"] != before
    assert entry["reason"] == "rate approved"
    assert entry["locked_by"] == "lead"
    assert _run(["lock", "check"], cwd=project_dir).exit_code == 0


def test_lock_set_dry_run_writes_nothing(project_dir):
    result = _run(["lock", "set", "--dry-run"], cwd=project_dir)
    assert result.exit_code == 0, result.output
    assert "dry run" in result.output
    assert not (project_dir / ".cdec" / "locks.yaml").exists()


def test_lock_list_shows_state(project_dir):
    _run(["lock", "set"], cwd=project_dir)
    result = _run(["lock", "list"], cwd=project_dir)
    assert result.exit_code == 0, result.output
    assert "ok" in result.output and "Invoice.settle" in result.output

    _edit(project_dir, "amount * 0.2", "amount * 0.3")
    result = _run(["lock", "list", "--json"], cwd=project_dir)
    rows = json.loads(result.output)["locks"]
    assert rows[0]["state"] == "CHANGED"


def test_lock_list_all_includes_unlocked_elements(project_dir):
    result = _run(["lock", "list", "--all"], cwd=project_dir)
    assert "Invoice.describe" in result.output


def test_lock_set_reports_a_lock_whose_tag_was_deleted(project_dir):
    """Deleting the tag and re-running `cdec lock set` is the obvious way to try
    to escape a lock; it must fail loudly rather than print 'nothing to do'."""
    _run(["lock", "set"], cwd=project_dir)
    _edit(project_dir, '    @locked(reason="agreed settlement order")\n', "")

    result = _run(["lock", "set"], cwd=project_dir)
    assert result.exit_code == 1
    assert "has lost its tag" in result.output
    assert "Invoice.settle" in result.output
    assert [e["target"] for e in _lockfile(project_dir)["locks"]] == ["Invoice.settle"]


def test_lock_set_force_prunes_a_released_lock(project_dir):
    _run(["lock", "set"], cwd=project_dir)
    _edit(project_dir, '    @locked(reason="agreed settlement order")\n', "")

    result = _run(["lock", "set", "--force"], cwd=project_dir)
    assert result.exit_code == 0, result.output
    assert "- released Invoice.settle" in result.output
    assert _lockfile(project_dir)["locks"] == []


def test_lock_remove_releases_a_lock(project_dir):
    _run(["lock", "set"], cwd=project_dir)
    result = _run(["lock", "remove", "--target", "Invoice.settle"], cwd=project_dir)
    assert result.exit_code == 0, result.output
    assert "- released Invoice.settle" in result.output
    assert _lockfile(project_dir)["locks"] == []


def test_lock_remove_reports_no_match(project_dir):
    _run(["lock", "set"], cwd=project_dir)
    result = _run(["lock", "remove", "--target", "Nope.*"], cwd=project_dir)
    assert result.exit_code == 1
    assert "no ledger entries match" in result.output


# ---------- glob-driven locking via config ----------

def test_config_globs_lock_without_a_tag(project_dir):
    (project_dir / ".cdec" / "config.yaml").write_text(
        CONFIG + "lock:\n  targets:\n    - \"Invoice.*\"\n", encoding="utf-8"
    )
    _run(["lock", "set"], cwd=project_dir)
    targets = {e["target"] for e in _lockfile(project_dir)["locks"]}
    assert targets == {"Invoice.settle", "Invoice.describe"}

    _edit(project_dir, 'return "invoice"', 'return "changed"')
    result = _run(["lock", "check"], cwd=project_dir)
    assert result.exit_code == 1
    assert "Invoice.describe" in result.output


# ---------- cdec check integration ----------

def test_check_fails_on_lock_drift(project_dir):
    _run(["lock", "set"], cwd=project_dir)
    _edit(project_dir, "amount * 0.2", "amount * 0.3")

    result = _run(["check"], cwd=project_dir)
    assert result.exit_code == 1
    assert "cdec lock: 1 lock violation(s)" in result.output


def test_check_passes_when_locks_hold(project_dir):
    _run(["lock", "set"], cwd=project_dir)
    result = _run(["check"], cwd=project_dir)
    assert result.exit_code == 0, result.output
    assert "1 locked element(s) verified" in result.output


def test_check_is_silent_for_a_project_with_nothing_locked(project_dir):
    """A project that never opted in must not suddenly see lock output."""
    (project_dir / "src_tree" / "billing.py").write_text(
        BILLING.replace('    @locked(reason="agreed settlement order")\n', ""),
        encoding="utf-8",
    )
    result = _run(["check"], cwd=project_dir)
    assert result.exit_code == 0, result.output
    assert "cdec lock" not in result.output


def test_check_fails_when_a_tag_was_never_baselined(project_dir):
    """Tagging @locked and forgetting `cdec lock set` verifies nothing, so it
    must not pass quietly — that would make the lock decorative."""
    assert not (project_dir / ".cdec" / "locks.yaml").exists()
    result = _run(["check"], cwd=project_dir)
    assert result.exit_code == 1
    assert "[missing]" in result.output
    assert "Invoice.settle" in result.output
    assert "cdec lock set" in result.output


def test_check_no_locks_flag_skips_verification(project_dir):
    _run(["lock", "set"], cwd=project_dir)
    _edit(project_dir, "amount * 0.2", "amount * 0.3")

    result = _run(["check", "--no-locks"], cwd=project_dir)
    assert result.exit_code == 0, result.output
    assert "cdec lock" not in result.output


def test_check_bypass_reports_loudly_but_passes(project_dir):
    _run(["lock", "set"], cwd=project_dir)
    _edit(project_dir, "amount * 0.2", "amount * 0.3")

    result = _run(
        ["check", "--bypass-locks", "--bypass-reason", "hotfix #42"], cwd=project_dir
    )
    assert result.exit_code == 0, result.output
    assert "LOCKS BYPASSED" in result.output
    assert "hotfix #42" in result.output
    assert "1 lock violation(s) suppressed" in result.output


def test_check_lock_disabled_in_config(project_dir):
    _run(["lock", "set"], cwd=project_dir)
    _edit(project_dir, "amount * 0.2", "amount * 0.3")
    (project_dir / ".cdec" / "config.yaml").write_text(
        CONFIG + "lock:\n  enabled: false\n", encoding="utf-8"
    )
    result = _run(["check"], cwd=project_dir)
    assert result.exit_code == 0, result.output
    # `cdec lock check` still verifies on demand even when `cdec check` skips it.
    assert _run(["lock", "check"], cwd=project_dir).exit_code == 1
