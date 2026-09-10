"""End-to-end CLI tests for implementation locks.

Locks are the `implementation-locks` rule type now, so everything here goes
through `cdec check`: verification is a plain run, baselining is
`--automatic-exceptions locks`, and re-baselining a drifted body adds `--force`.
The privilege boundary that split `lock set` from `lock set --force` is the
thing these tests exist to hold.
"""

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

SETTINGS = """\
language: python
source: src_tree
reference: .cdec/reference.xmi
"""

LOCK_RULE = """\
rules:
  - id: frozen-implementations
    type: implementation-locks
    severity: error
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


def _rules(project_dir: Path, body: str = LOCK_RULE) -> None:
    (project_dir / ".cdec" / "rules.yaml").write_text(
        SETTINGS + "\n" + body, encoding="utf-8"
    )


@pytest.fixture()
def project_dir(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    src = root / "src_tree"
    src.mkdir(parents=True)
    (src / "cdec_rules.py").write_text(PY_SHIM, encoding="utf-8")
    (src / "billing.py").write_text(BILLING, encoding="utf-8")
    (root / ".cdec").mkdir()
    _rules(root)
    return root


def _edit(project_dir: Path, old: str, new: str) -> None:
    path = project_dir / "src_tree" / "billing.py"
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new), encoding="utf-8")


def _doc(project_dir: Path) -> dict:
    return yaml.safe_load(
        (project_dir / ".cdec" / "rules.yaml").read_text(encoding="utf-8")
    )


def _locks(project_dir: Path) -> list:
    return _doc(project_dir).get("locks") or []


def _baseline(project_dir: Path, *extra: str):
    return _run(["check", "--automatic-exceptions", "locks", *extra], cwd=project_dir)


# ---------- recording the ledger ----------

def test_baselining_writes_the_ledger_into_rules_yaml(project_dir):
    result = _baseline(project_dir)
    assert result.exit_code == 0, result.output
    assert "+ locked   Invoice.settle" in result.output

    locks = _locks(project_dir)
    assert [e["target"] for e in locks] == ["Invoice.settle"]
    assert locks[0]["reason"] == "agreed settlement order"
    # The rules the user wrote are still there, in the same file.
    assert _doc(project_dir)["rules"][0]["id"] == "frozen-implementations"


def test_check_passes_on_a_clean_tree(project_dir):
    _baseline(project_dir)
    result = _run(["check"], cwd=project_dir)
    assert result.exit_code == 0, result.output
    assert "no violations" in result.output


def test_check_fails_on_a_changed_body(project_dir):
    _baseline(project_dir)
    _edit(project_dir, "amount * 0.2", "amount * 0.3")

    result = _run(["check"], cwd=project_dir)
    assert result.exit_code == 1
    assert "Invoice.settle" in result.output
    assert "frozen-implementations" in result.output
    assert "cdec check --automatic-exceptions locks --force" in result.output


def test_check_json_report_carries_the_lock_violation(project_dir):
    _baseline(project_dir)
    _edit(project_dir, "amount * 0.2", "amount * 0.3")

    out = project_dir / "report.json"
    result = _run(["check", "--json-out", str(out)], cwd=project_dir)
    assert result.exit_code == 1
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["summary"]["errors"] == 1
    violation = payload["violations"][0]
    assert violation["qualified_name"] == "Invoice.settle"
    assert violation["engine"] == "lock"
    assert violation["rule"] == "changed"
    assert violation["waivable"] is False
    assert violation["key"].startswith("L-")


def test_baselining_will_not_rebaseline_drift_without_force(project_dir):
    """The privilege boundary: an unforced run can never erase the evidence."""
    _baseline(project_dir)
    before = _locks(project_dir)[0]["digest"]
    _edit(project_dir, "amount * 0.2", "amount * 0.3")

    result = _baseline(project_dir)
    assert result.exit_code == 0, result.output
    assert "CHANGED" in result.output
    assert "--force" in result.output
    assert _locks(project_dir)[0]["digest"] == before
    # And the gate still fails, so nothing was quietly accepted.
    assert _run(["check"], cwd=project_dir).exit_code == 1


def test_force_rebaselines_a_drifted_body(project_dir):
    _baseline(project_dir)
    before = _locks(project_dir)[0]["digest"]
    _edit(project_dir, "amount * 0.2", "amount * 0.3")

    result = _baseline(project_dir, "--force")
    assert result.exit_code == 0, result.output
    assert "~ rebased  Invoice.settle" in result.output

    entry = _locks(project_dir)[0]
    assert entry["digest"] != before
    assert _run(["check"], cwd=project_dir).exit_code == 0


def test_deleting_the_tag_does_not_release_the_lock(project_dir):
    """Deleting the tag and re-baselining is the obvious way to try to escape a
    lock; it must fail loudly rather than print 'nothing to do'."""
    _baseline(project_dir)
    _edit(project_dir, '    @locked(reason="agreed settlement order")\n', "")

    result = _baseline(project_dir)
    assert result.exit_code == 0, result.output
    assert "STALE" in result.output
    assert "Invoice.settle" in result.output
    assert [e["target"] for e in _locks(project_dir)] == ["Invoice.settle"]
    # The ledger is the authority, so the gate keeps failing.
    check = _run(["check"], cwd=project_dir)
    assert check.exit_code == 1
    assert "Invoice.settle" in check.output


def test_force_prunes_a_released_lock(project_dir):
    _baseline(project_dir)
    _edit(project_dir, '    @locked(reason="agreed settlement order")\n', "")

    result = _baseline(project_dir, "--force")
    assert result.exit_code == 0, result.output
    assert "- released Invoice.settle" in result.output
    assert _locks(project_dir) == []
    assert _run(["check"], cwd=project_dir).exit_code == 0


def test_a_tag_that_was_never_baselined_fails_the_gate(project_dir):
    """Tagging @locked and forgetting to baseline verifies nothing, so it must
    not pass quietly — that would make the lock decorative."""
    assert not _locks(project_dir)
    result = _run(["check"], cwd=project_dir)
    assert result.exit_code == 1
    assert "Invoice.settle" in result.output
    assert "cdec check --automatic-exceptions locks" in result.output


def test_locks_are_not_acceptable_as_exceptions(project_dir):
    """The one thing `cdec exceptions` refuses, and the reason it exists."""
    _baseline(project_dir)
    _edit(project_dir, "amount * 0.2", "amount * 0.3")
    key = json.loads(
        _run(["exceptions", "review", "--format", "json"], cwd=project_dir).output
    )["issues"][0]["key"]
    assert key.startswith("L-")

    result = _run(["exceptions", "allow", key], cwd=project_dir)
    assert result.exit_code == 1
    assert "cannot be accepted as exceptions" in result.output
    assert "--automatic-exceptions locks --force" in result.output


def test_grandfathering_rules_never_swallows_a_lock_violation(project_dir):
    """`--automatic-exceptions rules` accepts what it can, and says loudly what
    it would not."""
    _baseline(project_dir)
    _edit(project_dir, "amount * 0.2", "amount * 0.3")

    result = _run(["check", "--automatic-exceptions", "rules"], cwd=project_dir)
    assert result.exit_code == 0, result.output
    assert "NOT grandfathered" in result.output
    assert _run(["check"], cwd=project_dir).exit_code == 1


# ---------- glob-driven locking via the rule ----------

def test_rule_targets_lock_without_a_tag(project_dir):
    _rules(project_dir, LOCK_RULE + '    targets: ["Invoice.*"]\n')
    _baseline(project_dir)
    assert {e["target"] for e in _locks(project_dir)} == {
        "Invoice.settle",
        "Invoice.describe",
    }

    _edit(project_dir, 'return "invoice"', 'return "changed"')
    result = _run(["check"], cwd=project_dir)
    assert result.exit_code == 1
    assert "Invoice.describe" in result.output


# ---------- opting out ----------

def test_no_lock_rule_means_no_lock_checking(project_dir):
    """A project that never wrote the rule must not suddenly see lock output —
    `cdec check` enforces what the file asks for, nothing more."""
    _rules(project_dir, "rules: []\n")
    result = _run(["check"], cwd=project_dir)
    assert result.exit_code == 0, result.output
    assert "Invoice.settle" not in result.output


def test_severity_off_disables_the_rule(project_dir):
    _baseline(project_dir)
    _edit(project_dir, "amount * 0.2", "amount * 0.3")
    _rules(
        project_dir,
        "rules:\n"
        "  - id: frozen-implementations\n"
        "    type: implementation-locks\n"
        "    severity: off\n",
    )
    result = _run(["check"], cwd=project_dir)
    assert result.exit_code == 0, result.output


def test_bypass_reports_loudly_but_passes(project_dir):
    _baseline(project_dir)
    _edit(project_dir, "amount * 0.2", "amount * 0.3")

    result = _run(
        ["check", "--bypass-locks", "--bypass-reason", "hotfix #42"], cwd=project_dir
    )
    assert result.exit_code == 0, result.output
    assert "LOCKS BYPASSED" in result.output
    assert "hotfix #42" in result.output
    assert "1 lock violation(s) suppressed" in result.output


def test_bypass_is_visible_in_the_json_report(project_dir):
    """CI has to be able to reject a bypassed run on a protected branch."""
    _baseline(project_dir)
    _edit(project_dir, "amount * 0.2", "amount * 0.3")
    out = project_dir / "report.json"
    _run(
        ["check", "--bypass-locks", "--bypass-reason", "hotfix #42",
         "--json-out", str(out)],
        cwd=project_dir,
    )
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["summary"]["bypassed"] is True
    assert payload["summary"]["bypass_reason"] == "hotfix #42"
    assert payload["bypassed"][0]["qualified_name"] == "Invoice.settle"


# ---------- identity ----------

def test_a_lock_is_an_ast_identity_not_a_line_range(project_dir):
    """Inserting code above a locked function must not trip it."""
    _baseline(project_dir)
    path = project_dir / "src_tree" / "billing.py"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "class Invoice:",
            "# a new comment\nHELPER = 1\n\n\nclass Invoice:",
        ),
        encoding="utf-8",
    )
    assert _run(["check"], cwd=project_dir).exit_code == 0


def test_an_unsupported_language_is_reported_as_skipped(tmp_path):
    """A rule that cannot run must say so — silence reads as 'clean'."""
    root = tmp_path / "proj"
    src = root / "src_tree"
    src.mkdir(parents=True)
    (src / "a.ts").write_text("export class Alpha {}\n", encoding="utf-8")
    (root / ".cdec").mkdir()
    (root / ".cdec" / "rules.yaml").write_text(
        "language: typescript\nsource: src_tree\n\n" + LOCK_RULE, encoding="utf-8"
    )
    result = _run(["check"], cwd=root)
    assert result.exit_code == 0, result.output
    assert "[skipped] frozen-implementations" in result.output
    assert "fingerprinter" in result.output
