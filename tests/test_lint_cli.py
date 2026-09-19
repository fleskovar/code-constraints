"""End-to-end CLI tests for `cdec init` and `cdec check`.

`cdec check` is the whole gate now, so this file also covers the paths that used
to belong to separate commands: `--automatic-exceptions reference` (was
`cdec reference update`) and `--automatic-exceptions rules` (was
`cdec check --update-baseline`).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
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


def _set_rules(config_dir: Path, rules_yaml: str) -> None:
    """Replace the `rules:` list, keeping the project settings above it.

    Settings and rules share one file now, so a test that wants a specific rule
    set can't just overwrite `rules.yaml` — it would drop `language:` and
    `source:` with it.
    """
    path = config_dir / "rules.yaml"
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    header = "".join(
        f"{key}: {doc[key]}\n"
        for key in ("language", "source", "reference")
        if doc.get(key) is not None
    )
    path.write_text(header + "\n" + rules_yaml, encoding="utf-8")


NO_NEW_CLASSES = (
    "rules:\n"
    "  - id: no-new-classes\n"
    "    type: no-new-classes\n"
    "    severity: error\n"
)


def test_init_creates_one_rules_file(project_dir):
    result = _run(
        ["init", "--lang", "python", "--source", "src_tree"],
        cwd=project_dir,
    )
    assert result.exit_code == 0, result.output
    cdec = project_dir / ".cdec"
    assert (cdec / "rules.yaml").is_file()
    assert (cdec / "reference.xmi").is_file()
    assert (cdec / "README.md").is_file()
    # ...plus the folder extra rule files go in. Scaffolded empty, so the split
    # is discoverable before anybody needs it.
    assert (cdec / "rules").is_dir()
    # The per-concern files are gone: settings, rules, exceptions and locks all
    # live in rules.yaml, which is the point of the layout.
    assert not (cdec / "config.yaml").exists()
    assert not (cdec / "baseline.yaml").exists()
    assert not (cdec / "locks.yaml").exists()


def test_init_scaffolds_usable_settings(project_dir):
    _run(["init", "--lang", "python", "--source", "src_tree"], cwd=project_dir)
    doc = yaml.safe_load(
        (project_dir / ".cdec" / "rules.yaml").read_text(encoding="utf-8")
    )
    assert doc["language"] == "python"
    assert doc["source"] == "src_tree"
    assert doc["rules"] == []


def test_init_refuses_overwrite_without_force(project_dir):
    _run(["init", "--lang", "python", "--source", "src_tree"], cwd=project_dir)
    result = _run(["init", "--lang", "python", "--source", "src_tree"], cwd=project_dir)
    assert result.exit_code == 1


def test_update_assets_reads_language_from_rules_yaml(project_dir):
    # `init` writes the language to rules.yaml only. Without --lang,
    # update-assets must find it there, not in the legacy config.yaml.
    _run(["init", "--lang", "csharp", "--source", "src_tree"], cwd=project_dir)
    result = _run(["update-assets", "--no-agents"], cwd=project_dir)
    assert result.exit_code == 0, result.output
    assert (project_dir / "CodeConstraintsRules.cs").is_file(), result.output


def test_check_no_violations_on_unchanged_source(project_dir):
    _run(["init", "--lang", "python", "--source", "src_tree"], cwd=project_dir)
    # rules.yaml ships with `rules: []` so check should pass.
    result = _run(["check"], cwd=project_dir)
    assert result.exit_code == 0, result.output
    assert "no violations" in result.output


def test_check_fires_on_new_class_after_init(project_dir):
    _run(["init", "--lang", "python", "--source", "src_tree"], cwd=project_dir)
    _set_rules(project_dir / ".cdec", NO_NEW_CLASSES)
    (project_dir / "src_tree" / "animals" / "cat.py").write_text(
        "class Cat:\n    name: str = ''\n",
        encoding="utf-8",
    )
    json_path = project_dir / "lint.json"
    result = _run(["check", "--json-out", str(json_path)], cwd=project_dir)
    assert result.exit_code == 1, result.output
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    qns = {v["qualified_name"] for v in payload["violations"]}
    assert any("Cat" in qn for qn in qns)


def test_automatic_exceptions_reference_resnapshots(project_dir):
    """`--automatic-exceptions reference` replaces `cdec reference update`."""
    _run(["init", "--lang", "python", "--source", "src_tree"], cwd=project_dir)
    _set_rules(
        project_dir / ".cdec",
        NO_NEW_CLASSES
        + "  - id: public-shape-is-frozen\n"
          "    type: reference-architecture\n"
          "    severity: error\n",
    )
    (project_dir / "src_tree" / "animals" / "cat.py").write_text(
        "class Cat:\n    pass\n",
        encoding="utf-8",
    )
    fail = _run(["check"], cwd=project_dir)
    assert fail.exit_code == 1
    refresh = _run(["check", "--automatic-exceptions", "reference"], cwd=project_dir)
    assert refresh.exit_code == 0, refresh.output
    assert "reference.xmi" in refresh.output
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
    start = result.output.index("{")
    end = result.output.rindex("}")
    payload = json.loads(result.output[start:end + 1])
    assert "violations" in payload


def test_automatic_exceptions_rules_grandfathers_violations(project_dir):
    """`--automatic-exceptions rules` replaces `cdec check --update-baseline`."""
    _run(["init", "--lang", "python", "--source", "src_tree"], cwd=project_dir)
    _set_rules(project_dir / ".cdec", NO_NEW_CLASSES)
    (project_dir / "src_tree" / "animals" / "cat.py").write_text(
        "class Cat:\n    pass\n",
        encoding="utf-8",
    )
    fail = _run(["check"], cwd=project_dir)
    assert fail.exit_code == 1
    rec = _run(["check", "--automatic-exceptions", "rules"], cwd=project_dir)
    assert rec.exit_code == 0, rec.output
    clean = _run(["check"], cwd=project_dir)
    assert clean.exit_code == 0, clean.output
    assert "silenced by an exception" in clean.output


def test_grandfathering_does_not_pre_approve_the_next_violation(project_dir):
    """The ratchet: today's violations are accepted, tomorrow's still fail."""
    _run(["init", "--lang", "python", "--source", "src_tree"], cwd=project_dir)
    _set_rules(project_dir / ".cdec", NO_NEW_CLASSES)
    (project_dir / "src_tree" / "animals" / "cat.py").write_text(
        "class Cat:\n    pass\n", encoding="utf-8"
    )
    _run(["check", "--automatic-exceptions", "rules"], cwd=project_dir)
    assert _run(["check"], cwd=project_dir).exit_code == 0

    (project_dir / "src_tree" / "animals" / "lion.py").write_text(
        "class Lion:\n    pass\n", encoding="utf-8"
    )
    result = _run(["check"], cwd=project_dir)
    assert result.exit_code == 1, result.output
    assert "Lion" in result.output
    assert "Cat" not in result.output


def test_exceptions_are_written_into_rules_yaml(project_dir):
    """The whole point of the layout: one committed file carries the decision."""
    _run(["init", "--lang", "python", "--source", "src_tree"], cwd=project_dir)
    _set_rules(project_dir / ".cdec", NO_NEW_CLASSES)
    (project_dir / "src_tree" / "animals" / "cat.py").write_text(
        "class Cat:\n    pass\n", encoding="utf-8"
    )
    _run(["check", "--automatic-exceptions", "rules"], cwd=project_dir)
    doc = yaml.safe_load(
        (project_dir / ".cdec" / "rules.yaml").read_text(encoding="utf-8")
    )
    assert doc["rules"], "the hand-written rules must survive the write"
    assert doc["exceptions"], "the accepted violation must land in the same file"
    assert any("Cat" in e["qualified_name"] for e in doc["exceptions"])


def test_writing_exceptions_preserves_comments_and_messages(project_dir):
    """A tool write must not reflow the file a human maintains."""
    _run(["init", "--lang", "python", "--source", "src_tree"], cwd=project_dir)
    path = project_dir / ".cdec" / "rules.yaml"
    _set_rules(
        project_dir / ".cdec",
        "# A comment nobody should lose.\n"
        "rules:\n"
        "  - id: no-new-classes\n"
        "    type: no-new-classes\n"
        "    severity: error\n"
        "    message: |\n"
        "      Line one of the explanation.\n"
        "      Line two of the explanation.\n",
    )
    before = path.read_text(encoding="utf-8")
    (project_dir / "src_tree" / "animals" / "cat.py").write_text(
        "class Cat:\n    pass\n", encoding="utf-8"
    )
    _run(["check", "--automatic-exceptions", "rules"], cwd=project_dir)
    after = path.read_text(encoding="utf-8")

    assert "# A comment nobody should lose." in after
    assert "Line one of the explanation." in after
    assert "Line two of the explanation." in after
    assert after.startswith(before.rstrip("\n"))


def test_unknown_rule_type_names_the_known_ones(project_dir):
    _run(["init", "--lang", "python", "--source", "src_tree"], cwd=project_dir)
    _set_rules(
        project_dir / ".cdec",
        "rules:\n  - id: nope\n    type: not-a-real-rule\n    severity: error\n",
    )
    result = _run(["check"], cwd=project_dir)
    assert result.exit_code == 2
    assert "tag-conformance" in result.output
    assert "implementation-locks" in result.output


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
def test_csharp_demo_reports_its_seeded_violation():
    """The bundled demo seeds one conformance bug, and `cdec check` is now what
    catches it — there is no second command to run."""
    result = _run(
        ["check", "--config", str(CSHARP_DEMO / ".cdec"), "--source", str(CSHARP_DEMO)],
    )
    assert result.exit_code == 1, result.output
    assert "tags-must-be-honoured" in result.output


@pytest.mark.skipif(not PYTHON_DEMO_EXAMPLE.is_dir(), reason="examples/python_demo not present")
def test_python_demo_reports_its_seeded_violation():
    result = _run(
        [
            "check",
            "--config", str(PYTHON_DEMO_EXAMPLE / ".cdec"),
            "--source", str(PYTHON_DEMO_EXAMPLE),
        ],
    )
    assert result.exit_code == 1, result.output
    assert "tags-must-be-honoured" in result.output
    # The model-level rules still pass; only the tag rule fires.
    assert "animals-must-not-depend-on-store" not in result.output


@pytest.mark.skipif(not PYTHON_DEMO_EXAMPLE.is_dir(), reason="examples/python_demo not present")
def test_python_demo_model_rules_pass_on_their_own():
    """With the source-level rules switched off, the demo's model rules are clean."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        shadow = Path(tmp) / "python_demo"
        shutil.copytree(PYTHON_DEMO_EXAMPLE, shadow)
        path = shadow / ".cdec" / "rules.yaml"
        text = path.read_text(encoding="utf-8")
        text = text.replace(
            "  - id: tags-must-be-honoured\n    type: tag-conformance\n    severity: error\n",
            "  - id: tags-must-be-honoured\n    type: tag-conformance\n    severity: off\n",
        )
        path.write_text(text, encoding="utf-8")
        result = _run(["check", "--config", str(shadow / ".cdec"), "--source", str(shadow)])
        assert result.exit_code == 0, result.output


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
    _set_rules(proj / ".cdec", NO_NEW_CLASSES)
    # Need to commit the new file so it's parseable from the working tree
    # (cdec check parses the on-disk source). The --base-ref points at HEAD~0
    # before this commit.
    subprocess.run(["git", "-C", str(proj), "add", "."], check=True)
    subprocess.run(["git", "-C", str(proj), "commit", "-q", "-m", "add cat"], check=True)
    result = _run(["check", "--base-ref", "HEAD~1"], cwd=proj)
    assert result.exit_code == 1, result.output
    assert "Cat" in result.output


# ---------------------------------------------------------------------------
# Migration off the old per-concern files.
# ---------------------------------------------------------------------------

def test_migrate_folds_the_legacy_files_into_rules_yaml(project_dir):
    cdec = project_dir / ".cdec"
    cdec.mkdir()
    (cdec / "config.yaml").write_text(
        "language: python\nsource: src_tree\n"
        "baseline:\n  reference: .cdec/reference.xmi\n"
        "lock:\n  enabled: true\n  include_docstrings: false\n  targets: ['orders.**']\n",
        encoding="utf-8",
    )
    (cdec / "rules.yaml").write_text(
        "# Hand-written and full of explanation.\n" + NO_NEW_CLASSES, encoding="utf-8"
    )
    (cdec / "baseline.yaml").write_text(
        "violations:\n"
        "  no-new-classes:\n"
        "    - qualified_name: animals.Cat\n"
        "      reason: legacy, ARCH-42\n",
        encoding="utf-8",
    )
    (cdec / "locks.yaml").write_text(
        "version: 1\nlocks:\n"
        "- target: orders.Receipt.formatted\n"
        "  kind: method\n  algo: py-ast/1\n  digest: abc123\n",
        encoding="utf-8",
    )

    result = _run(["init", "--migrate"], cwd=project_dir)
    assert result.exit_code == 0, result.output

    assert not (cdec / "config.yaml").exists()
    assert not (cdec / "baseline.yaml").exists()
    assert not (cdec / "locks.yaml").exists()

    doc = yaml.safe_load((cdec / "rules.yaml").read_text(encoding="utf-8"))
    assert doc["language"] == "python"
    assert doc["source"] == "src_tree"
    assert doc["rules"][0]["id"] == "no-new-classes"
    assert doc["exceptions"][0]["qualified_name"] == "animals.Cat"
    assert doc["exceptions"][0]["reason"] == "legacy, ARCH-42"
    assert doc["locks"][0]["target"] == "orders.Receipt.formatted"
    # A `lock:` settings block becomes a real rule, since locks are a rule now.
    lock_rules = [r for r in doc["rules"] if r["type"] == "implementation-locks"]
    assert lock_rules and lock_rules[0]["targets"] == ["orders.**"]
    # And the hand-written comment survives.
    assert "# Hand-written and full of explanation." in (cdec / "rules.yaml").read_text(
        encoding="utf-8"
    )


def test_migrate_on_an_already_migrated_project_is_a_no_op(project_dir):
    _run(["init", "--lang", "python", "--source", "src_tree"], cwd=project_dir)
    result = _run(["init", "--migrate"], cwd=project_dir)
    assert result.exit_code == 0, result.output
    assert "nothing to migrate" in result.output


def test_a_legacy_layout_still_checks_without_migrating(project_dir):
    """An un-migrated project keeps working; it is told, not broken."""
    cdec = project_dir / ".cdec"
    cdec.mkdir()
    (cdec / "config.yaml").write_text(
        "language: python\nsource: src_tree\n", encoding="utf-8"
    )
    (cdec / "rules.yaml").write_text(NO_NEW_CLASSES, encoding="utf-8")
    (cdec / "baseline.yaml").write_text("violations: {}\n", encoding="utf-8")

    result = _run(["check"], cwd=project_dir)
    assert result.exit_code == 0, result.output
    assert "cdec init --migrate" in result.output


# ---------------------------------------------------------------------------
# The two rule layouts: `rules:` in rules.yaml, or `.cdec/rules/*.yaml`
# ---------------------------------------------------------------------------

DANGLING_RULES = (
    "rules:\n"
    "  - id: no-dangling\n"
    "    type: dangling-classes\n"
    "    severity: error\n"
)

FANOUT_RULES = (
    "rules:\n"
    "  - id: fanout\n"
    "    type: max-class-fanout\n"
    "    severity: error\n"
    "    limit: 0\n"
)


def _folder_project(project_dir: Path) -> Path:
    """An initialised project whose laws sit in two files under `.cdec/rules/`."""
    _run(["init", "--lang", "python", "--source", "src_tree"], cwd=project_dir)
    config_dir = project_dir / ".cdec"
    _set_rules(config_dir, "")  # settings only: the folder holds the laws
    folder = config_dir / "rules"
    folder.mkdir(exist_ok=True)
    (folder / "shape.yaml").write_text(DANGLING_RULES, encoding="utf-8")
    (folder / "size.yaml").write_text(FANOUT_RULES, encoding="utf-8")
    return config_dir


def _violated_rules(result) -> set:
    return {v["rule_id"] for v in json.loads(result.output)["violations"]}


def test_check_runs_every_file_in_the_rules_folder(project_dir):
    _folder_project(project_dir)
    result = _run(["check", "--format", "json"], cwd=project_dir)
    assert _violated_rules(result) == {"fanout", "no-dangling"}
    assert result.exit_code == 1, result.output


def test_a_single_rules_yaml_still_runs_on_its_own(project_dir):
    """The original layout is the whole gate for a project that never splits."""
    _run(["init", "--lang", "python", "--source", "src_tree"], cwd=project_dir)
    _set_rules(project_dir / ".cdec", FANOUT_RULES)
    result = _run(["check", "--format", "json"], cwd=project_dir)
    assert _violated_rules(result) == {"fanout"}


def test_rules_in_both_layouts_fail_the_run(project_dir):
    """The two are alternatives. Running one and ignoring the other silently
    would drop laws the team committed."""
    config_dir = _folder_project(project_dir)
    _set_rules(config_dir, FANOUT_RULES)  # now declared in both places
    result = _run(["check"], cwd=project_dir)
    assert result.exit_code == 2
    assert "two places" in result.output


def test_rules_file_flag_runs_only_that_file(project_dir):
    _folder_project(project_dir)
    assert _violated_rules(
        _run(["check", "--format", "json", "--rules-file", "shape"], cwd=project_dir)
    ) == {"no-dangling"}
    # Short form, and the name resolves with the extension too.
    assert _violated_rules(
        _run(["check", "--format", "json", "-R", "size.yaml"], cwd=project_dir)
    ) == {"fanout"}
    # Several at once, comma-separated.
    assert _violated_rules(
        _run(["check", "--format", "json", "-R", "shape,size"], cwd=project_dir)
    ) == {"fanout", "no-dangling"}


def test_exception_keys_survive_running_a_subset(project_dir):
    """A key names the issue, not the file its rule was configured in.

    Accepting something during a full run has to keep it accepted during the
    cheap run, or the two gates disagree about what is already decided.
    """
    _folder_project(project_dir)
    full = _run(["check", "--format", "json"], cwd=project_dir)
    subset = _run(["check", "--format", "json", "-R", "shape"], cwd=project_dir)
    shape_keys = {v["key"] for v in json.loads(subset.output)["violations"]}
    assert shape_keys
    assert shape_keys < {v["key"] for v in json.loads(full.output)["violations"]}

    key = min(shape_keys)
    allowed = _run(["exceptions", "allow", key, "--reason", "agreed"], cwd=project_dir)
    assert allowed.exit_code == 0, allowed.output
    after = _run(["check", "--format", "json", "-R", "shape"], cwd=project_dir)
    assert key not in {v["key"] for v in json.loads(after.output)["violations"]}
    # ...and it was recorded in rules.yaml, the one file the tool writes.
    assert key in (project_dir / ".cdec" / "rules.yaml").read_text(encoding="utf-8")


def test_an_unknown_rules_file_fails_before_parsing(project_dir):
    _folder_project(project_dir)
    result = _run(["check", "--rules-file", "typo"], cwd=project_dir)
    assert result.exit_code == 2
    assert "typo" in result.output
    assert "shape.yaml" in result.output  # it lists what does exist
