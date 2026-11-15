"""The guided journey: the project history, the edits of the `rules:` list, the
rule gallery, and the web endpoints behind the guide, rules and history pages."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from code_constraints import journal
from code_constraints.cli.__main__ import app as cli_app
from code_constraints.cli.scaffold import init_cdec_config
from code_constraints.core import rulesdoc
from code_constraints.core.model import Class, Package, Project
from code_constraints.lint.config import ConfigError, build_rule, load_rules
from code_constraints.lint.rules import known_rule_types
from code_constraints.lint.starters import starters
from code_constraints.web.app import app

FIXTURE = (Path(__file__).parent / "fixtures" / "python_demo").resolve()

def _copy_fixture(root: Path) -> None:
    """The fixture carries a `.cdec/` of its own. These tests scaffold one."""
    shutil.copytree(FIXTURE, root, ignore=shutil.ignore_patterns(".cdec", "__pycache__"))


FANOUT = "id: fanout\ntype: max-class-fanout\nseverity: error\nlimit: 0\n"


def _model(*names: str) -> Project:
    classes = [Class(name=n, qualified_name=f"app.{n}") for n in names]
    return Project(
        source_language="python",
        packages=[Package(name="app", qualified_name="app", classes=classes)],
    )


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A copy of the Python fixture with a scaffolded `.cdec/`."""
    root = tmp_path / "proj"
    _copy_fixture(root)
    init_cdec_config(root / ".cdec", "python", Path("."), force=False, parse_from=root)
    return root


@pytest.fixture
def client() -> TestClient:
    # The endpoints that write into `.cdec/` answer this machine only.
    return TestClient(app, client=("127.0.0.1", 50000))


def _register(client: TestClient, root: Path) -> str:
    r = client.post("/api/projects", json={"path": str(root), "lang": "python"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


# ---------- the `rules:` list ----------

def test_append_rule_keeps_every_comment(project: Path) -> None:
    path = project / ".cdec" / "rules.yaml"
    before = path.read_text(encoding="utf-8")
    rulesdoc.append_rule(path, {"id": "a", "type": "no-new-classes", "message": "one\ntwo\n"})
    rulesdoc.append_rule(path, {"id": "b", "type": "max-class-fanout", "limit": 3})
    after = path.read_text(encoding="utf-8")
    assert [r["id"] for r in rulesdoc.load_document(path)["rules"]] == ["a", "b"]
    # Every line of the hand-written file is still there, in order.
    kept = [line for line in before.splitlines() if line != "rules: []"]
    position = 0
    for line in kept:
        position = after.index(line, position)
    assert "message: |" in after


def test_set_rule_severity_changes_one_entry(project: Path) -> None:
    path = project / ".cdec" / "rules.yaml"
    rulesdoc.append_rule(path, {"id": "a", "type": "no-new-classes", "severity": "error"})
    rulesdoc.append_rule(path, {"id": "b", "type": "max-class-fanout"})
    rulesdoc.set_rule_severity(path, "a", "off")
    rulesdoc.set_rule_severity(path, "b", "warning")  # had no severity line
    rules = {r["id"]: r for r in rulesdoc.load_document(path)["rules"]}
    assert rules["a"]["severity"] == "off"
    assert rules["b"]["severity"] == "warning"
    assert [r.rule_id for r in load_rules(project / ".cdec").rules] == ["b"]


def test_an_edit_that_cannot_be_checked_leaves_the_file_unchanged(tmp_path: Path) -> None:
    path = tmp_path / "rules.yaml"
    text = "language: python\nsource: .\nrules: [{id: a, type: no-new-classes}]\n"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(rulesdoc.RulesFileError):
        rulesdoc.append_rule(path, {"id": "b", "type": "max-class-fanout"})
    assert path.read_text(encoding="utf-8") == text


# ---------- the gallery ----------

def test_every_rule_type_has_a_starter_that_builds() -> None:
    gallery = starters()
    assert sorted(s["type"] for s in gallery) == known_rule_types()
    for starter in gallery:
        assert build_rule(starter["entry"]) is not None, starter["type"]


def test_build_rule_refuses_an_id_that_is_taken() -> None:
    with pytest.raises(ConfigError):
        build_rule({"id": "a", "type": "no-new-classes"}, {"a"})


# ---------- the history ----------

def test_init_records_the_start_of_the_journey(project: Path) -> None:
    (start,) = journal.entries(project / ".cdec")
    assert (start.kind, start.journey, start.reference) == ("start", "brownfield", True)
    assert start.stats["classes"] > 0
    assert journal.model_path(project / ".cdec", start.id).is_file()


def test_an_empty_tree_starts_a_greenfield_journey(tmp_path: Path) -> None:
    init_cdec_config(tmp_path / ".cdec", "python", Path("."), force=False, parse_from=tmp_path)
    assert journal.entries(tmp_path / ".cdec")[0].journey == "greenfield"


def test_a_checkpoint_measures_the_distance_to_the_open_goal(tmp_path: Path) -> None:
    cfg = tmp_path / ".cdec"
    journal.record(cfg, "start", "Start", _model("A", "Old"), reference=True)
    assert journal.open_goal(journal.entries(cfg)) is None
    goal = journal.record(cfg, "goal", "Split A", _model("A", "B", "C"), reference=True)
    assert goal is not None and journal.open_goal(journal.entries(cfg)).id == goal.id  # type: ignore[union-attr]

    progress = journal.record(cfg, "checkpoint", "Half way", _model("A", "B", "Old"))
    assert progress is not None and progress.goal == goal.id
    assert progress.distance == {"to_build": 1, "unplanned": 1, "to_change": 0}

    # A re-snapshot of the reference closes the goal.
    journal.record(cfg, "checkpoint", "Done", _model("A", "B", "C"), reference=True)
    history = journal.entries(cfg)
    assert journal.open_goal(history) is None
    assert [e.kind for e in history] == ["start", "goal", "checkpoint", "checkpoint"]


def test_history_false_turns_the_history_off(tmp_path: Path) -> None:
    cfg = tmp_path / ".cdec"
    cfg.mkdir()
    (cfg / "rules.yaml").write_text("language: python\nsource: .\nhistory: false\n", encoding="utf-8")
    assert journal.record(cfg, "checkpoint", "x", _model("A")) is None
    assert journal.entries(cfg) == []


def test_reference_resnapshot_works_without_a_reference_rule(project: Path) -> None:
    """`-A reference` refreshes the baseline of the diff rules. It did nothing
    when no `reference-architecture` rule was on."""
    (project / "extra.py").write_text("class Extra:\n    pass\n", encoding="utf-8")
    cfg = project / ".cdec"
    result = CliRunner().invoke(
        cli_app, ["check", "--config", str(cfg), "-A", "reference", "-m", "added Extra"]
    )
    assert result.exit_code == 0, result.output
    assert "Extra" in (cfg / "reference.xmi").read_text(encoding="utf-8")
    last = journal.entries(cfg)[-1]
    assert (last.kind, last.note, last.reference) == ("checkpoint", "added Extra", True)


def test_reference_set_records_a_goal(project: Path) -> None:
    cfg = project / ".cdec"
    result = CliRunner().invoke(
        cli_app,
        ["reference", "set", str(cfg / "reference.xmi"), "--config", str(cfg),
         "--title", "Target", "-m", "why"],
    )
    assert result.exit_code == 0, result.output
    goal = journal.open_goal(journal.entries(cfg))
    assert goal is not None and (goal.title, goal.note) == ("Target", "why")


# ---------- the web endpoints ----------

def test_guide_sets_up_a_project(client: TestClient, tmp_path: Path) -> None:
    root = tmp_path / "proj"
    _copy_fixture(root)
    pid = _register(client, root)
    assert client.get(f"/api/projects/{pid}/journey").json()["configured"] is False

    r = client.post(f"/api/projects/{pid}/journey/init", json={"journey": "brownfield"})
    assert r.status_code == 200, r.text
    status = r.json()
    assert status["configured"] and status["reference"] and status["journey"] == "brownfield"
    assert (status["rules"], status["history"], status["rules_editable"]) == (0, 1, True)
    # A second init must not overwrite the config.
    assert client.post(
        f"/api/projects/{pid}/journey/init", json={"journey": "brownfield"}
    ).status_code == 409


def test_a_rule_is_previewed_then_turned_on_without_new_failures(
    client: TestClient, project: Path
) -> None:
    pid = _register(client, project)
    rules_file = project / ".cdec" / "rules.yaml"
    before = rules_file.read_text(encoding="utf-8")

    preview = client.post(f"/api/projects/{pid}/rules/preview", json={"yaml": FANOUT})
    assert preview.status_code == 200, preview.text
    found = preview.json()["open"]
    assert found > 0
    assert rules_file.read_text(encoding="utf-8") == before  # a preview writes nothing

    r = client.post(
        f"/api/projects/{pid}/rules", json={"yaml": FANOUT, "accept_existing": True}
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"id": "fanout", "accepted": found}

    overview = client.get(f"/api/projects/{pid}/rules").json()
    (rule,) = overview["rules"]
    assert (rule["id"], rule["open"], rule["accepted"]) == ("fanout", 0, found)
    # The gate agrees: the rule is on and nothing fails.
    check = CliRunner().invoke(cli_app, ["check", "--config", str(project / ".cdec")])
    assert check.exit_code == 0, check.output

    # The same id cannot be added twice.
    assert client.post(f"/api/projects/{pid}/rules", json={"yaml": FANOUT}).status_code == 400


def test_issues_are_accepted_and_a_rule_is_turned_off(client: TestClient, project: Path) -> None:
    pid = _register(client, project)
    assert client.post(f"/api/projects/{pid}/rules", json={"yaml": FANOUT}).status_code == 200
    issues = client.get(f"/api/projects/{pid}/rules").json()["issues"]
    key = issues[0]["key"]

    r = client.post(f"/api/projects/{pid}/exceptions", json={"keys": [key], "reason": "legacy"})
    assert r.json()["allowed"] == 1
    after = client.get(f"/api/projects/{pid}/rules").json()
    accepted = next(i for i in after["issues"] if i["key"] == key)
    assert accepted["waived"] and accepted["waiver_reason"] == "legacy"

    assert client.put(
        f"/api/projects/{pid}/rules/fanout", json={"severity": "off"}
    ).status_code == 204
    assert client.get(f"/api/projects/{pid}/rules").json()["rules"][0]["severity"] == "off"


def test_history_frames_show_the_change_between_two_entries(
    client: TestClient, project: Path
) -> None:
    pid = _register(client, project)
    (project / "extra.py").write_text("class Extra:\n    pass\n", encoding="utf-8")
    r = client.post(f"/api/projects/{pid}/history", json={"title": "Added Extra", "note": "why"})
    assert r.status_code == 200, r.text

    start, checkpoint = client.get(f"/api/projects/{pid}/history").json()
    assert (start["kind"], checkpoint["kind"], checkpoint["note"]) == ("start", "checkpoint", "why")

    frame = client.post(
        f"/api/projects/{pid}/history/frame",
        json={"entry": checkpoint["id"], "against": start["id"]},
    )
    assert frame.status_code == 200, frame.text
    changes = client.get(f"/api/xmi/{frame.json()['id']}/changes").json()
    assert [(c["classQname"].split(".")[-1], c["kind"]) for c in changes] == [("Extra", "added")]

    bad = client.post(f"/api/projects/{pid}/history/frame", json={"entry": "../../x"})
    assert bad.status_code == 404


def test_set_reference_from_the_editor_records_a_goal(client: TestClient, project: Path) -> None:
    pid = _register(client, project)
    body = (project / ".cdec" / "reference.xmi").read_bytes()
    r = client.put(
        f"/api/projects/{pid}/reference?kind=goal&title=Target&note=because", content=body
    )
    assert r.status_code == 200, r.text
    goal = client.get(f"/api/projects/{pid}/journey").json()["goal"]
    assert (goal["title"], goal["note"]) == ("Target", "because")


def test_a_remote_client_cannot_change_the_rules(project: Path) -> None:
    local = TestClient(app, client=("127.0.0.1", 50000))
    pid = _register(local, project)
    remote = TestClient(app, client=("192.168.1.20", 50000))
    for method, url, body in (
        ("post", f"/api/projects/{pid}/rules", {"yaml": FANOUT}),
        ("put", f"/api/projects/{pid}/rules/fanout", {"severity": "off"}),
        ("post", f"/api/projects/{pid}/exceptions", {"keys": ["V-00000000"]}),
        ("post", f"/api/projects/{pid}/history", {"title": "x"}),
    ):
        assert getattr(remote, method)(url, json=body).status_code == 403, url
