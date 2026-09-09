"""End-to-end CLI tests for `cdec init` and `cdec check`."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from code_constraints.cli.__main__ import app


FIXTURE_SRC = Path(__file__).parent / "fixtures" / "python_demo"


@pytest.fixture
def project_dir(tmp_path):
    """A fresh copy of python_demo at the root of a tmp folder."""
    dst = tmp_path / "proj"
    shutil.copytree(FIXTURE_SRC, dst / "src_tree")
    return dst


def _run(args, cwd=None):
    runner = CliRunner()
    if cwd is None:
        return runner.invoke(app, args)
    # Typer's CliRunner doesn't accept cwd; use a wrapper.
    import os
    here = os.getcwd()
    try:
        os.chdir(cwd)
        return runner.invoke(app, args)
    finally:
        os.chdir(here)


def test_init_creates_cdec_folder(project_dir):
    result = _run(
        ["init", "--lang", "python", "--source", "src_tree"],
        cwd=project_dir,
    )
    assert result.exit_code == 0, result.output
    uml = project_dir / ".cdec"
    assert (uml / "config.yaml").is_file()
    assert (uml / "rules.yaml").is_file()
    assert (uml / "baseline.yaml").is_file()
    assert (uml / "reference.xmi").is_file()
    assert (uml / "README.md").is_file()


def test_init_refuses_overwrite_without_force(project_dir):
    _run(["init", "--lang", "python", "--source", "src_tree"], cwd=project_dir)
    result = _run(["init", "--lang", "python", "--source", "src_tree"], cwd=project_dir)
    assert result.exit_code == 1


def test_check_no_violations_on_unchanged_source(project_dir):
    _run(["init", "--lang", "python", "--source", "src_tree"], cwd=project_dir)
    # rules.yaml ships with `rules: []` so check should pass.
    result = _run(["check"], cwd=project_dir)
    assert result.exit_code == 0, result.output
    assert "no violations" in result.output


def test_check_fires_on_new_class_after_init(project_dir):
    _run(["init", "--lang", "python", "--source", "src_tree"], cwd=project_dir)
    # Append a no-new-classes rule.
    rules_path = project_dir / ".cdec" / "rules.yaml"
    rules_path.write_text(
        "rules:\n"
        "  - id: no-new-classes\n"
        "    type: no-new-classes\n"
        "    severity: error\n",
        encoding="utf-8",
    )
    # Add a brand-new class to the source tree.
    (project_dir / "src_tree" / "animals" / "cat.py").write_text(
        "class Cat:\n    name: str = ''\n",
        encoding="utf-8",
    )
    json_path = project_dir / "lint.json"
    result = _run(
        ["check", "--json-out", str(json_path)],
        cwd=project_dir,
    )
    assert result.exit_code == 1, result.output
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    qns = {v["qualified_name"] for v in payload["violations"]}
    assert any("Cat" in qn for qn in qns)


def test_check_update_reference_then_clean(project_dir):
    _run(["init", "--lang", "python", "--source", "src_tree"], cwd=project_dir)
    (project_dir / ".cdec" / "rules.yaml").write_text(
        "rules:\n  - id: no-new-classes\n    type: no-new-classes\n    severity: error\n",
        encoding="utf-8",
    )
    (project_dir / "src_tree" / "animals" / "cat.py").write_text(
        "class Cat:\n    pass\n",
        encoding="utf-8",
    )
    fail = _run(["check"], cwd=project_dir)
    assert fail.exit_code == 1
    refresh = _run(["check", "--update-reference"], cwd=project_dir)
    assert refresh.exit_code == 0, refresh.output
    clean = _run(["check"], cwd=project_dir)
    assert clean.exit_code == 0, clean.output


def test_check_log_out_writes_human_text(project_dir):
    _run(["init", "--lang", "python", "--source", "src_tree"], cwd=project_dir)
    log_path = project_dir / "lint.log"
    result = _run(["check", "--log-out", str(log_path)], cwd=project_dir)
    assert result.exit_code == 0, result.output
    assert log_path.is_file()
    assert "no violations" in log_path.read_text(encoding="utf-8")


def test_check_format_json_outputs_json(project_dir):
    _run(["init", "--lang", "python", "--source", "src_tree"], cwd=project_dir)
    result = _run(["check", "--format", "json"], cwd=project_dir)
    assert result.exit_code == 0, result.output
    # Find the JSON object in stdout (may be preceded by other writes).
    start = result.output.index("{")
    # The JSON payload ends at the last `}` before any subsequent typer.echo lines.
    end = result.output.rindex("}")
    payload = json.loads(result.output[start:end + 1])
    assert "violations" in payload


def test_check_baseline_silences_violations(project_dir):
    _run(["init", "--lang", "python", "--source", "src_tree"], cwd=project_dir)
    (project_dir / ".cdec" / "rules.yaml").write_text(
        "rules:\n  - id: no-new-classes\n    type: no-new-classes\n    severity: error\n",
        encoding="utf-8",
    )
    (project_dir / "src_tree" / "animals" / "cat.py").write_text(
        "class Cat:\n    pass\n",
        encoding="utf-8",
    )
    fail = _run(["check"], cwd=project_dir)
    assert fail.exit_code == 1
    # Record current violations as baseline.
    rec = _run(["check", "--update-baseline"], cwd=project_dir)
    assert rec.exit_code == 0, rec.output
    # Re-run: should now pass because the violation is in the baseline.
    clean = _run(["check"], cwd=project_dir)
    assert clean.exit_code == 0, clean.output


def test_python_demo_bundled_config_passes():
    """The .cdec/ folder shipped with tests/fixtures/python_demo must lint clean."""
    result = _run(
        [
            "check",
            "--config", str(FIXTURE_SRC / ".cdec"),
            "--source", str(FIXTURE_SRC),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "no violations" in result.output


CSHARP_DEMO = Path(__file__).parent.parent / "examples" / "csharp_demo"
PYTHON_DEMO_EXAMPLE = Path(__file__).parent.parent / "examples" / "python_demo"


@pytest.mark.skipif(not CSHARP_DEMO.is_dir(), reason="examples/csharp_demo not present")
def test_csharp_demo_bundled_config_passes():
    """The .cdec/ folder shipped with examples/csharp_demo must lint clean."""
    result = _run(
        [
            "check",
            "--config", str(CSHARP_DEMO / ".cdec"),
            "--source", str(CSHARP_DEMO),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "no violations" in result.output


@pytest.mark.skipif(not PYTHON_DEMO_EXAMPLE.is_dir(), reason="examples/python_demo not present")
def test_python_demo_example_bundled_config_passes():
    """The .cdec/ folder shipped with examples/python_demo must lint clean."""
    result = _run(
        [
            "check",
            "--config", str(PYTHON_DEMO_EXAMPLE / ".cdec"),
            "--source", str(PYTHON_DEMO_EXAMPLE),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "no violations" in result.output


def test_python_demo_rule_fires_when_invariant_broken(tmp_path):
    """Drop a `store` reference into an `animals` file and the layering rule must fail."""
    shadow = tmp_path / "python_demo"
    shutil.copytree(FIXTURE_SRC, shadow)
    # Add an Animal attribute typed as Cart — violates
    # animals-must-not-depend-on-store (severity: error in the demo config).
    (shadow / "animals" / "watcher.py").write_text(
        "from store.cart import Cart\n"
        "\n"
        "\n"
        "class Watcher:\n"
        "    cart: Cart = None\n",
        encoding="utf-8",
    )
    result = _run([
        "check",
        "--config", str(shadow / ".cdec"),
        "--source", str(shadow),
    ])
    assert result.exit_code == 1, result.output
    assert "animals-must-not-depend-on-store" in result.output


def test_check_base_ref_path(tmp_path):
    """Use a synthetic two-commit git repo to drive --base-ref."""
    proj = tmp_path / "gitproj"
    src = proj / "src_tree"
    shutil.copytree(FIXTURE_SRC, src)
    # Initialise a git repo with the fixture as initial commit.
    subprocess.run(["git", "init", "-q", str(proj)], check=True)
    subprocess.run(["git", "-C", str(proj), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(proj), "config", "user.name", "Test"], check=True)
    subprocess.run(["git", "-C", str(proj), "config", "commit.gpgsign", "false"], check=True)
    subprocess.run(["git", "-C", str(proj), "add", "."], check=True)
    subprocess.run(["git", "-C", str(proj), "commit", "-q", "-m", "initial"], check=True)
    # Now scaffold .cdec (no reference, so we exercise --base-ref).
    _run(["init", "--lang", "python", "--source", "src_tree"], cwd=proj)
    # Add a new class and DO NOT commit — we want it as working tree.
    (src / "animals" / "cat.py").write_text("class Cat:\n    pass\n", encoding="utf-8")
    (proj / ".cdec" / "rules.yaml").write_text(
        "rules:\n  - id: no-new-classes\n    type: no-new-classes\n    severity: error\n",
        encoding="utf-8",
    )
    # Need to commit the new file so it's parseable from the working tree
    # (cdec check parses the on-disk source). The --base-ref points at HEAD~0
    # before this commit.
    subprocess.run(["git", "-C", str(proj), "add", "."], check=True)
    subprocess.run(["git", "-C", str(proj), "commit", "-q", "-m", "add cat"], check=True)
    result = _run(["check", "--base-ref", "HEAD~1"], cwd=proj)
    assert result.exit_code == 1, result.output
    assert "Cat" in result.output
