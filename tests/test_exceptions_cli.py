"""End-to-end tests for `cdec exceptions` — the review loop.

The scenario each test builds on is the one the feature exists for: a project
with a reference baseline gets a change that violates a rule, and the team
decides to accept it rather than revert it. The decision lands in the
`exceptions:` section of `.cdec/rules.yaml`, next to the rule it exempts.
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
    "language: python\n"
    "source: src_tree\n"
    "reference: .cdec/reference.xmi\n"
    "\n"
    "rules:\n  - id: no-new-classes\n    type: no-new-classes\n    severity: error\n"
)


def _rules_file(project) -> Path:
    return project / ".cdec" / "rules.yaml"


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
    result = _run(["exceptions", "review", "--out", str(out)], cwd=project)
    assert result.exit_code == 0, result.output
    text = out.read_text(encoding="utf-8")
    issue_lines = [ln for ln in text.splitlines() if ln.startswith("- ")]
    assert len(issue_lines) == 1
    assert "animals.Cat" in issue_lines[0]


def test_patch_applies_marked_lines_and_check_then_passes(project):
    out = project / "review.txt"
    _run(["exceptions", "review", "--out", str(out)], cwd=project)
    marked = out.read_text(encoding="utf-8").replace("- [V", "- [ALLOW] [V")
    out.write_text(marked, encoding="utf-8")

    patched = _run(["exceptions", "patch", "--file", str(out)], cwd=project)
    assert patched.exit_code == 0, patched.output
    assert _run(["check"], cwd=project).exit_code == 0


def test_patch_records_the_inline_reason(project):
    out = project / "review.txt"
    _run(["exceptions", "review", "--out", str(out)], cwd=project)
    out.write_text(
        out.read_text(encoding="utf-8").replace(
            "- [V", "- [ALLOW: agreed in ARCH-42] [V"
        ),
        encoding="utf-8",
    )
    _run(["exceptions", "patch", "--file", str(out)], cwd=project)
    listing = _run(["exceptions", "list"], cwd=project)
    assert "agreed in ARCH-42" in listing.output


def test_patch_leaves_unmarked_issues_blocking(project):
    """Two violations, one accepted: the other must still fail the build."""
    (project / "src_tree" / "animals" / "lion.py").write_text(
        "class Lion:\n    pass\n", encoding="utf-8"
    )
    out = project / "review.txt"
    _run(["exceptions", "review", "--out", str(out)], cwd=project)
    lines = out.read_text(encoding="utf-8").splitlines()
    marked = [
        ("- [ALLOW] " + ln[2:]) if ln.startswith("- ") and "animals.Cat" in ln else ln
        for ln in lines
    ]
    out.write_text("\n".join(marked), encoding="utf-8")
    _run(["exceptions", "patch", "--file", str(out)], cwd=project)

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
    result = _run(["exceptions", "patch", "--file", str(log)], cwd=project)
    assert result.exit_code == 0, result.output
    assert _run(["check"], cwd=project).exit_code == 0


def test_patch_dry_run_writes_nothing(project):
    out = project / "review.txt"
    _run(["exceptions", "review", "--out", str(out)], cwd=project)
    out.write_text(
        out.read_text(encoding="utf-8").replace("- [V", "- [ALLOW] [V"), encoding="utf-8"
    )
    before = _rules_file(project).read_text(encoding="utf-8")
    result = _run(["exceptions", "patch", "--file", str(out), "--dry-run"], cwd=project)
    assert result.exit_code == 0, result.output
    assert _rules_file(project).read_text(encoding="utf-8") == before
    assert _run(["check"], cwd=project).exit_code == 1


def test_patch_with_no_marks_is_a_no_op(project):
    out = project / "review.txt"
    _run(["exceptions", "review", "--out", str(out)], cwd=project)
    result = _run(["exceptions", "patch", "--file", str(out)], cwd=project)
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
            app, ["exceptions", "patch", "--file", "-"], input=f"- [ALLOW] [{key}]\n"
        )
    finally:
        os.chdir(here)
    assert result.exit_code == 0, result.output
    assert _run(["check"], cwd=project).exit_code == 0


# ---------------- allow / remove by key ----------------

def test_allow_by_key(project):
    key = _only_key(_run(["check"], cwd=project).output)
    result = _run(["exceptions", "allow", key, "--reason", "agreed"], cwd=project)
    assert result.exit_code == 0, result.output
    assert _run(["check"], cwd=project).exit_code == 0


def test_allow_is_idempotent(project):
    key = _only_key(_run(["check"], cwd=project).output)
    _run(["exceptions", "allow", key], cwd=project)
    again = _run(["exceptions", "allow", key], cwd=project)
    assert again.exit_code == 0, again.output
    assert "already allowed" in again.output


def test_allow_rejects_an_unknown_key(project):
    result = _run(["exceptions", "allow", "V-00000000"], cwd=project)
    assert result.exit_code == 1
    assert "unknown key" in result.output
    assert _run(["check"], cwd=project).exit_code == 1


def test_allow_rejects_a_malformed_key(project):
    result = _run(["exceptions", "allow", "not-a-key"], cwd=project)
    assert result.exit_code == 1
    assert "not a valid issue key" in result.output


def test_remove_makes_the_issue_block_again(project):
    key = _only_key(_run(["check"], cwd=project).output)
    _run(["exceptions", "allow", key], cwd=project)
    assert _run(["check"], cwd=project).exit_code == 0

    removed = _run(["exceptions", "remove", key], cwd=project)
    assert removed.exit_code == 0, removed.output
    assert _run(["check"], cwd=project).exit_code == 1


def test_remove_of_an_unwaived_key_fails_loudly(project):
    key = _only_key(_run(["check"], cwd=project).output)
    result = _run(["exceptions", "remove", key], cwd=project)
    assert result.exit_code == 1
    assert "nothing to remove" in result.output


def test_patch_remove_mark_withdraws_a_waiver(project):
    key = _only_key(_run(["check"], cwd=project).output)
    _run(["exceptions", "allow", key], cwd=project)
    patch_file = project / "withdraw.txt"
    patch_file.write_text(f"- [REMOVE] [{key}]\n", encoding="utf-8")
    result = _run(["exceptions", "patch", "--file", str(patch_file)], cwd=project)
    assert result.exit_code == 0, result.output
    assert _run(["check"], cwd=project).exit_code == 1


# ---------------- list / prune ----------------

def test_list_reports_nothing_on_a_fresh_project(project):
    result = _run(["exceptions", "list"], cwd=project)
    assert result.exit_code == 0
    assert "no exceptions" in result.output


def test_list_json_is_machine_readable(project):
    key = _only_key(_run(["check"], cwd=project).output)
    _run(["exceptions", "allow", key, "--reason", "agreed"], cwd=project)
    result = _run(["exceptions", "list", "--format", "json"], cwd=project)
    payload = json.loads(result.output[result.output.index("[") :])
    assert payload[0]["key"] == key
    assert payload[0]["reason"] == "agreed"


def test_prune_drops_waivers_whose_issue_is_gone(project):
    key = _only_key(_run(["check"], cwd=project).output)
    _run(["exceptions", "allow", key], cwd=project)
    (project / "src_tree" / "animals" / "cat.py").unlink()

    result = _run(["exceptions", "prune"], cwd=project)
    assert result.exit_code == 0, result.output
    assert key in result.output
    assert "no exceptions" in _run(["exceptions", "list"], cwd=project).output


def test_prune_keeps_waivers_that_still_apply(project):
    key = _only_key(_run(["check"], cwd=project).output)
    _run(["exceptions", "allow", key], cwd=project)
    result = _run(["exceptions", "prune"], cwd=project)
    assert "no stale exceptions" in result.output
    assert _run(["check"], cwd=project).exit_code == 0


# ---------------- conformance findings (Engine B) ----------------

@pytest.mark.skipif(not PYTHON_DEMO_EXAMPLE.is_dir(), reason="examples/python_demo absent")
def test_tag_conformance_findings_can_be_accepted(tmp_path):
    """Engine B findings come through `cdec check` now, and keep their `F-` keys
    — so an exception recorded before the CLI was unified still resolves."""
    root = tmp_path / "demo"
    shutil.copytree(PYTHON_DEMO_EXAMPLE, root)

    before = _run(["check"], cwd=root)
    assert before.exit_code == 1
    keys = [k for k in find_keys(before.output) if k.startswith("F-")]
    assert keys

    for key in keys:
        assert _run(["exceptions", "allow", key, "--reason", "seeded"], cwd=root).exit_code == 0

    after = _run(["check"], cwd=root)
    assert after.exit_code == 0, after.output
    assert "silenced by an exception" in after.output


@pytest.mark.skipif(not PYTHON_DEMO_EXAMPLE.is_dir(), reason="examples/python_demo absent")
def test_an_exception_key_does_not_move_when_the_rule_is_renamed(tmp_path):
    """A key names the issue, not the `rules.yaml` entry that surfaced it."""
    root = tmp_path / "demo"
    shutil.copytree(PYTHON_DEMO_EXAMPLE, root)
    keys = [k for k in find_keys(_run(["check"], cwd=root).output) if k.startswith("F-")]
    for key in keys:
        _run(["exceptions", "allow", key, "--reason", "seeded"], cwd=root)
    assert _run(["check"], cwd=root).exit_code == 0

    rules = root / ".cdec" / "rules.yaml"
    rules.write_text(
        rules.read_text(encoding="utf-8").replace(
            "id: tags-must-be-honoured", "id: tags-are-a-promise"
        ),
        encoding="utf-8",
    )
    assert _run(["check"], cwd=root).exit_code == 0, "renaming the entry broke the exception"


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

    refused = _run(["exceptions", "allow", lock_keys[0]], cwd=root)
    assert refused.exit_code == 1
    # The refusal must hand over the privileged command, not just say no.
    assert "cdec check --automatic-exceptions locks --force" in refused.output
    assert _run(["check"], cwd=root).exit_code == 1


# ---------------- the old command name still points somewhere ----------------

def test_baseline_is_a_hidden_alias_for_exceptions(project):
    """`cdec baseline` was the old name; a script that still uses it must work."""
    key = _only_key(_run(["check"], cwd=project).output)
    result = _run(["baseline", "allow", key, "--reason", "agreed"], cwd=project)
    assert result.exit_code == 0, result.output
    assert _run(["check"], cwd=project).exit_code == 0


def test_retired_commands_say_where_the_behaviour_went(project):
    """A bare "No such command" teaches nothing; each retired command points at
    the rule type that replaced it."""
    enforce = _run(["enforce", "src_tree", "--lang", "python"], cwd=project)
    assert enforce.exit_code == 2
    assert "tag-conformance" in enforce.output

    lock = _run(["lock", "set"], cwd=project)
    assert lock.exit_code == 2
    assert "implementation-locks" in lock.output
    assert "--automatic-exceptions locks" in lock.output

    ref = _run(["reference", "test"], cwd=project)
    assert ref.exit_code == 2
    assert "reference-architecture" in ref.output

    update = _run(["reference", "update"], cwd=project)
    assert update.exit_code == 2
    assert "--automatic-exceptions reference" in update.output
