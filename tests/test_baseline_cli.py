"""End-to-end tests for `cdec baseline` — the review loop.

The scenario each test builds on is the one the feature exists for: a project
with a reference baseline gets a change that violates a rule, and the team
decides to accept it rather than revert it.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from code_constraints.cli.__main__ import app
from code_constraints.core.keys import find_keys

FIXTURE_SRC = Path(__file__).parent / "fixtures" / "python_demo"
PYTHON_DEMO_EXAMPLE = Path(__file__).parent.parent / "examples" / "python_demo"

RULES_NO_NEW_CLASSES = (
    "rules:\n  - id: no-new-classes\n    type: no-new-classes\n    severity: error\n"
)


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


@pytest.fixture
def project(tmp_path):
    """A scaffolded project whose source has drifted: one new class."""
    root = tmp_path / "proj"
    shutil.copytree(FIXTURE_SRC, root / "src_tree")
    shutil.rmtree(root / "src_tree" / ".cdec", ignore_errors=True)
    _run(["init", "--lang", "python", "--source", "src_tree"], cwd=root)
    (root / ".cdec" / "rules.yaml").write_text(RULES_NO_NEW_CLASSES, encoding="utf-8")
    (root / "src_tree" / "animals" / "cat.py").write_text(
        "class Cat:\n    pass\n", encoding="utf-8"
    )
    return root


def _only_key(text: str) -> str:
    keys = find_keys(text)
    assert len(keys) == 1, f"expected exactly one key in:\n{text}"
    return keys[0]


# ---------------- keys in the report ----------------

def test_check_report_carries_a_key(project):
    result = _run(["check"], cwd=project)
    assert result.exit_code == 1, result.output
    assert _only_key(result.output).startswith("V-")


def test_keys_are_stable_across_runs(project):
    first = _run(["check"], cwd=project)
    second = _run(["check"], cwd=project)
    assert _only_key(first.output) == _only_key(second.output)


def test_key_survives_an_unrelated_edit(project):
    """Inserting lines above the offending class must not change its key —
    otherwise every waiver would expire on the next reformat."""
    before = _only_key(_run(["check"], cwd=project).output)
    cat = project / "src_tree" / "animals" / "cat.py"
    cat.write_text("# a comment\n\n\n" + cat.read_text(encoding="utf-8"), encoding="utf-8")
    assert _only_key(_run(["check"], cwd=project).output) == before


def test_json_report_carries_keys(project):
    out = project / "lint.json"
    _run(["check", "--json-out", str(out)], cwd=project)
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["violations"][0]["key"].startswith("V-")


# ---------------- review → patch ----------------

def test_review_writes_one_line_per_issue(project):
    out = project / "review.txt"
    result = _run(["baseline", "review", "--out", str(out)], cwd=project)
    assert result.exit_code == 0, result.output
    text = out.read_text(encoding="utf-8")
    issue_lines = [ln for ln in text.splitlines() if ln.startswith("- ")]
    assert len(issue_lines) == 1
    assert "animals.Cat" in issue_lines[0]


def test_patch_applies_marked_lines_and_check_then_passes(project):
    out = project / "review.txt"
    _run(["baseline", "review", "--out", str(out)], cwd=project)
    marked = out.read_text(encoding="utf-8").replace("- [V", "- [ALLOW] [V")
    out.write_text(marked, encoding="utf-8")

    patched = _run(["baseline", "patch", "--file", str(out)], cwd=project)
    assert patched.exit_code == 0, patched.output
    assert _run(["check"], cwd=project).exit_code == 0


def test_patch_records_the_inline_reason(project):
    out = project / "review.txt"
    _run(["baseline", "review", "--out", str(out)], cwd=project)
    out.write_text(
        out.read_text(encoding="utf-8").replace(
            "- [V", "- [ALLOW: agreed in ARCH-42] [V"
        ),
        encoding="utf-8",
    )
    _run(["baseline", "patch", "--file", str(out)], cwd=project)
    listing = _run(["baseline", "list"], cwd=project)
    assert "agreed in ARCH-42" in listing.output


def test_patch_leaves_unmarked_issues_blocking(project):
    """Two violations, one accepted: the other must still fail the build."""
    (project / "src_tree" / "animals" / "lion.py").write_text(
        "class Lion:\n    pass\n", encoding="utf-8"
    )
    out = project / "review.txt"
    _run(["baseline", "review", "--out", str(out)], cwd=project)
    lines = out.read_text(encoding="utf-8").splitlines()
    marked = [
        ("- [ALLOW] " + ln[2:]) if ln.startswith("- ") and "animals.Cat" in ln else ln
        for ln in lines
    ]
    out.write_text("\n".join(marked), encoding="utf-8")
    _run(["baseline", "patch", "--file", str(out)], cwd=project)

    after = _run(["check"], cwd=project)
    assert after.exit_code == 1
    assert "animals.Lion" in after.output
    assert "animals.Cat" not in after.output


def test_check_log_out_is_directly_patchable(project):
    """The plain check log doubles as a review file — no extra step needed."""
    log = project / "check.log"
    _run(["check", "--log-out", str(log)], cwd=project)
    log.write_text(
        log.read_text(encoding="utf-8").replace("  - [V", "  - [ALLOW] [V"),
        encoding="utf-8",
    )
    result = _run(["baseline", "patch", "--file", str(log)], cwd=project)
    assert result.exit_code == 0, result.output
    assert _run(["check"], cwd=project).exit_code == 0


def test_patch_dry_run_writes_nothing(project):
    out = project / "review.txt"
    _run(["baseline", "review", "--out", str(out)], cwd=project)
    out.write_text(
        out.read_text(encoding="utf-8").replace("- [V", "- [ALLOW] [V"), encoding="utf-8"
    )
    before = (project / ".cdec" / "baseline.yaml").read_text(encoding="utf-8")
    result = _run(["baseline", "patch", "--file", str(out), "--dry-run"], cwd=project)
    assert result.exit_code == 0, result.output
    assert (project / ".cdec" / "baseline.yaml").read_text(encoding="utf-8") == before
    assert _run(["check"], cwd=project).exit_code == 1


def test_patch_with_no_marks_is_a_no_op(project):
    out = project / "review.txt"
    _run(["baseline", "review", "--out", str(out)], cwd=project)
    result = _run(["baseline", "patch", "--file", str(out)], cwd=project)
    assert result.exit_code == 0
    assert "nothing to apply" in result.output
    assert _run(["check"], cwd=project).exit_code == 1


def test_patch_reads_stdin(project):
    key = _only_key(_run(["check"], cwd=project).output)
    runner = CliRunner()
    here = os.getcwd()
    try:
        os.chdir(project)
        result = runner.invoke(
            app, ["baseline", "patch", "--file", "-"], input=f"- [ALLOW] [{key}]\n"
        )
    finally:
        os.chdir(here)
    assert result.exit_code == 0, result.output
    assert _run(["check"], cwd=project).exit_code == 0


# ---------------- allow / remove by key ----------------

def test_allow_by_key(project):
    key = _only_key(_run(["check"], cwd=project).output)
    result = _run(["baseline", "allow", key, "--reason", "agreed"], cwd=project)
    assert result.exit_code == 0, result.output
    assert _run(["check"], cwd=project).exit_code == 0


def test_allow_is_idempotent(project):
    key = _only_key(_run(["check"], cwd=project).output)
    _run(["baseline", "allow", key], cwd=project)
    again = _run(["baseline", "allow", key], cwd=project)
    assert again.exit_code == 0, again.output
    assert "already allowed" in again.output


def test_allow_rejects_an_unknown_key(project):
    result = _run(["baseline", "allow", "V-00000000"], cwd=project)
    assert result.exit_code == 1
    assert "unknown key" in result.output
    assert _run(["check"], cwd=project).exit_code == 1


def test_allow_rejects_a_malformed_key(project):
    result = _run(["baseline", "allow", "not-a-key"], cwd=project)
    assert result.exit_code == 1
    assert "not a valid issue key" in result.output


def test_remove_makes_the_issue_block_again(project):
    key = _only_key(_run(["check"], cwd=project).output)
    _run(["baseline", "allow", key], cwd=project)
    assert _run(["check"], cwd=project).exit_code == 0

    removed = _run(["baseline", "remove", key], cwd=project)
    assert removed.exit_code == 0, removed.output
    assert _run(["check"], cwd=project).exit_code == 1


def test_remove_of_an_unwaived_key_fails_loudly(project):
    key = _only_key(_run(["check"], cwd=project).output)
    result = _run(["baseline", "remove", key], cwd=project)
    assert result.exit_code == 1
    assert "nothing to remove" in result.output


def test_patch_remove_mark_withdraws_a_waiver(project):
    key = _only_key(_run(["check"], cwd=project).output)
    _run(["baseline", "allow", key], cwd=project)
    patch_file = project / "withdraw.txt"
    patch_file.write_text(f"- [REMOVE] [{key}]\n", encoding="utf-8")
    result = _run(["baseline", "patch", "--file", str(patch_file)], cwd=project)
    assert result.exit_code == 0, result.output
    assert _run(["check"], cwd=project).exit_code == 1


# ---------------- list / prune ----------------

def test_list_reports_nothing_on_a_fresh_project(project):
    result = _run(["baseline", "list"], cwd=project)
    assert result.exit_code == 0
    assert "no waivers" in result.output


def test_list_json_is_machine_readable(project):
    key = _only_key(_run(["check"], cwd=project).output)
    _run(["baseline", "allow", key, "--reason", "agreed"], cwd=project)
    result = _run(["baseline", "list", "--format", "json"], cwd=project)
    payload = json.loads(result.output[result.output.index("[") :])
    assert payload[0]["key"] == key
    assert payload[0]["reason"] == "agreed"


def test_prune_drops_waivers_whose_issue_is_gone(project):
    key = _only_key(_run(["check"], cwd=project).output)
    _run(["baseline", "allow", key], cwd=project)
    (project / "src_tree" / "animals" / "cat.py").unlink()

    result = _run(["baseline", "prune"], cwd=project)
    assert result.exit_code == 0, result.output
    assert key in result.output
    assert "no waivers" in _run(["baseline", "list"], cwd=project).output


def test_prune_keeps_waivers_that_still_apply(project):
    key = _only_key(_run(["check"], cwd=project).output)
    _run(["baseline", "allow", key], cwd=project)
    result = _run(["baseline", "prune"], cwd=project)
    assert "no stale waivers" in result.output
    assert _run(["check"], cwd=project).exit_code == 0


# ---------------- conformance findings (Engine B) ----------------

@pytest.mark.skipif(not PYTHON_DEMO_EXAMPLE.is_dir(), reason="examples/python_demo absent")
def test_enforce_findings_can_be_waived(tmp_path):
    root = tmp_path / "demo"
    shutil.copytree(PYTHON_DEMO_EXAMPLE, root)

    before = _run(["enforce", ".", "--lang", "python"], cwd=root)
    assert before.exit_code == 1
    keys = [k for k in find_keys(before.output) if k.startswith("F-")]
    assert keys

    for key in keys:
        assert _run(["baseline", "allow", key, "--reason", "seeded"], cwd=root).exit_code == 0

    after = _run(["enforce", ".", "--lang", "python"], cwd=root)
    assert after.exit_code == 0, after.output
    assert "silenced by baseline" in after.output
    # …and the escape hatch still shows them.
    assert _run(["enforce", ".", "--lang", "python", "--no-baseline"], cwd=root).exit_code == 1


@pytest.mark.skipif(not PYTHON_DEMO_EXAMPLE.is_dir(), reason="examples/python_demo absent")
def test_waiving_a_finding_leaves_drift_waivers_alone(tmp_path):
    """`check --update-baseline` rewrites the drift section; it must not take
    conformance waivers with it."""
    root = tmp_path / "demo"
    shutil.copytree(PYTHON_DEMO_EXAMPLE, root)
    findings = _run(["enforce", ".", "--lang", "python"], cwd=root)
    key = [k for k in find_keys(findings.output) if k.startswith("F-")][0]
    _run(["baseline", "allow", key], cwd=root)

    _run(["check", "--update-baseline"], cwd=root)
    listing = _run(["baseline", "list", "--engine", "enforce"], cwd=root)
    assert key in listing.output


# ---------------- locks are not waivable ----------------

@pytest.mark.skipif(not PYTHON_DEMO_EXAMPLE.is_dir(), reason="examples/python_demo absent")
def test_lock_violation_is_reported_with_a_key_but_refused(tmp_path):
    root = tmp_path / "demo"
    shutil.copytree(PYTHON_DEMO_EXAMPLE, root)
    billing = root / "orders" / "billing.py"
    billing.write_text(
        billing.read_text(encoding="utf-8").replace(" line(s) — ", " line(s), "),
        encoding="utf-8",
    )

    check = _run(["check"], cwd=root)
    assert check.exit_code == 1
    lock_keys = [k for k in find_keys(check.output) if k.startswith("L-")]
    assert lock_keys

    refused = _run(["baseline", "allow", lock_keys[0]], cwd=root)
    assert refused.exit_code == 1
    # The refusal must hand over the privileged command, not just say no.
    assert "cdec lock set" in refused.output
    assert _run(["check"], cwd=root).exit_code == 1
