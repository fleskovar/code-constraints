"""`cdec ui` with no argument: the start folder, the folder browser, the model
references, the check with a chosen subject and baseline, and the rule changes
in the history."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from code_constraints import journal
from code_constraints.cli.scaffold import init_cdec_config
from code_constraints.core.model_io import load_model, save_model
from code_constraints.web.app import app

FIXTURE = (Path(__file__).parent / "fixtures" / "python_demo").resolve()
FANOUT = {"id": "fanout", "type": "max-class-fanout", "severity": "error", "limit": 0}


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, client=("127.0.0.1", 50000))


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    shutil.copytree(FIXTURE, root, ignore=shutil.ignore_patterns(".cdec", "__pycache__"))
    init_cdec_config(root / ".cdec", "python", Path("."), force=False, parse_from=root)
    return root


def _register(client: TestClient, root: Path) -> str:
    r = client.post("/api/projects", json={"path": str(root), "lang": "python"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _statuses(client: TestClient, xmi_id: str) -> dict[str, str]:
    graph = client.get(f"/api/xmi/{xmi_id}/model", params={"diagram": "class"}).json()
    return {n["qualifiedName"]: n["status"] for n in graph["nodes"]}


def _without_class(root: Path, name: str, out: Path) -> Path:
    """The reference model with one class removed, as a model file."""
    model = load_model(root / ".cdec" / "reference.xmi")
    for package in model.packages:
        package.classes = [c for c in package.classes if c.name != name]
    save_model(model, out)
    return out


# ---------- the start folder and the folder browser ----------

def test_start_offers_the_project_of_the_working_folder(
    client: TestClient, project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(project)
    start = client.get("/api/start").json()
    assert start["configured"] is True and start["lang"] == "python"
    assert Path(start["path"]) == project


def test_start_detects_a_folder_with_no_config(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "a.py").write_text("class A: pass\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    start = client.get("/api/start").json()
    assert start == {**start, "configured": False, "lang": "python", "path": str(tmp_path)}


def test_folder_browser_lists_folders_and_marks_projects(
    client: TestClient, project: Path
) -> None:
    (project.parent / "plain").mkdir()
    (project.parent / "file.txt").write_text("x", encoding="utf-8")
    listing = client.get("/api/fs", params={"path": str(project.parent)}).json()
    assert {f["name"]: f["project"] for f in listing["folders"]} == {"plain": False, "proj": True}
    assert Path(listing["parent"]) == project.parent.parent
    # A hidden folder is not a place for source code.
    assert ".cdec" not in [f["name"] for f in client.get("/api/fs", params={"path": str(project)}).json()["folders"]]
    assert client.get("/api/fs", params={"path": str(project / "nope")}).status_code == 400


def test_folder_browser_is_for_this_machine_only(project: Path) -> None:
    remote = TestClient(app, client=("203.0.113.9", 50000))
    assert remote.get("/api/fs", params={"path": str(project)}).status_code == 403
    assert remote.get("/api/start").status_code == 403


# ---------- model references ----------

def test_models_show_and_compare(client: TestClient, project: Path, tmp_path: Path) -> None:
    pid = _register(client, project)
    start = journal.entries(project / ".cdec")[0]
    refs = [m["ref"] for m in client.get(f"/api/projects/{pid}/models").json()]
    assert refs[:3] == ["code", "reference", f"history:{start.id}"]

    file = _without_class(project, "Dog", tmp_path / "old.json")
    with file.open("rb") as fh:
        up = client.post(f"/api/projects/{pid}/models/upload", files={"model": ("old.json", fh)})
    assert up.status_code == 200, up.text
    ref = up.json()["ref"]
    assert ref in [m["ref"] for m in client.get(f"/api/projects/{pid}/models").json()]

    def show(show: str, against: str = "") -> dict[str, str]:
        r = client.post(f"/api/projects/{pid}/models/show", json={"show": show, "against": against})
        assert r.status_code == 200, r.text
        return _statuses(client, r.json()["id"])

    # Green is in the shown model only. Red is in the other model only.
    assert show("code", ref)["animals.Dog"] == "added"
    assert show(ref, "code")["animals.Dog"] == "removed"
    assert set(show(f"history:{start.id}").values()) == {"unchanged"}
    assert "animals.Dog" not in show(ref)

    for bad in ("history:nope", "upload:nope", "what"):
        r = client.post(f"/api/projects/{pid}/models/show", json={"show": bad})
        assert r.status_code == 404, bad


def test_a_model_file_opens_with_no_project(client: TestClient, project: Path) -> None:
    with (project / ".cdec" / "reference.xmi").open("rb") as fh:
        r = client.post("/api/models/open", files={"model": ("reference.xmi", fh)})
    assert r.status_code == 200, r.text
    assert "animals.Dog" in _statuses(client, r.json()["id"])
    r = client.post("/api/models/open", files={"model": ("notes.txt", b"x")})
    assert r.status_code == 400


# ---------- the check with a chosen subject and baseline ----------

def test_check_against_another_baseline(client: TestClient, project: Path, tmp_path: Path) -> None:
    pid = _register(client, project)
    rule = {"id": "frozen", "type": "no-new-classes", "severity": "error"}
    assert client.post(f"/api/projects/{pid}/rules", json={"entry": rule}).status_code == 200
    file = _without_class(project, "Dog", tmp_path / "old.json")
    with file.open("rb") as fh:
        ref = client.post(f"/api/projects/{pid}/models/upload", files={"model": ("old.json", fh)}).json()["ref"]

    default = client.get(f"/api/projects/{pid}/rules").json()
    assert default["default_inputs"] is True and default["issues"] == []
    other = client.get(f"/api/projects/{pid}/rules", params={"baseline": ref}).json()
    assert other["default_inputs"] is False
    assert [i["qualified_name"] for i in other["issues"]] == ["animals.Dog"]


def test_check_of_a_model_skips_the_rules_that_read_source(client: TestClient, project: Path) -> None:
    pid = _register(client, project)
    for entry in (FANOUT, {"id": "tags", "type": "tag-conformance"}):
        assert client.post(f"/api/projects/{pid}/rules", json={"entry": entry}).status_code == 200
    report = client.get(f"/api/projects/{pid}/rules", params={"subject": "reference"}).json()
    by_id = {r["id"]: r for r in report["rules"]}
    assert by_id["fanout"]["open"] > 0 and not by_id["fanout"]["skipped"]
    assert "no source tree" in by_id["tags"]["skipped"]


# ---------- rule changes in the history ----------

def test_rule_changes_are_history_entries(client: TestClient, project: Path) -> None:
    pid = _register(client, project)
    client.post(f"/api/projects/{pid}/rules", json={"entry": FANOUT})
    client.put(f"/api/projects/{pid}/rules/fanout", json={"severity": "warning"})
    client.delete(f"/api/projects/{pid}/rules/fanout")
    history = journal.entries(project / ".cdec")
    assert [(e.kind, e.title) for e in history[1:]] == [
        ("rules", "Rule fanout turned on"),
        ("rules", "Rule fanout: severity warning"),
        ("rules", "Rule fanout removed"),
    ]
    assert [[r["severity"] for r in e.rules] for e in history[1:]] == [["error"], ["warning"], []]
    # A rule change is not a goal and not a new reference.
    assert journal.open_goal(history) is None and not any(e.reference for e in history[1:])


def test_a_comparison_is_not_a_reference(client: TestClient, project: Path, tmp_path: Path) -> None:
    pid = _register(client, project)
    file = _without_class(project, "Dog", tmp_path / "old.json")
    with file.open("rb") as fh:
        ref = client.post(f"/api/projects/{pid}/models/upload", files={"model": ("old.json", fh)}).json()["ref"]
    diff = client.post(f"/api/projects/{pid}/models/show", json={"show": "code", "against": ref}).json()
    body = client.get(f"/api/xmi/{diff['id']}/source").content
    before = (project / ".cdec" / "reference.xmi").read_bytes()
    r = client.put(f"/api/projects/{pid}/reference", content=body)
    assert r.status_code == 400 and "comparison" in r.text
    assert (project / ".cdec" / "reference.xmi").read_bytes() == before


# ---------- `cdec check` from the viewer ----------

DEMO = (Path(__file__).parent.parent / "examples" / "python_demo").resolve()


@pytest.fixture
def demo(tmp_path: Path) -> Path:
    root = tmp_path / "demo"
    shutil.copytree(DEMO, root, ignore=shutil.ignore_patterns("__pycache__"))
    return root


def _cli_check(root: Path, *args: str) -> tuple[int, dict]:
    import json
    import os

    from typer.testing import CliRunner

    from code_constraints.cli.__main__ import app as cli

    prev = os.getcwd()
    os.chdir(root)
    try:
        result = CliRunner().invoke(cli, ["check", "--format", "json", *args])
    finally:
        os.chdir(prev)
    return result.exit_code, json.loads(result.stdout)


def test_the_viewer_check_is_the_cli_check(
    client: TestClient, demo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pid = _register(client, demo)
    monkeypatch.chdir(demo)
    for fail_on in ("error", "none"):
        exit_code, cli_report = _cli_check(demo, "--fail-on", fail_on)
        r = client.post(f"/api/projects/{pid}/check", json={"fail_on": fail_on})
        assert r.status_code == 200, r.text
        run = r.json()
        assert run["report"] == cli_report
        assert run["exit_code"] == exit_code and run["passed"] is (exit_code == 0)
        assert run["acceptable"] is True
    # The demo has one seeded violation, so the default run fails.
    assert client.post(f"/api/projects/{pid}/check", json={}).json()["exit_code"] == 1
    assert run["command"] == "cdec check --fail-on none"
    assert "Summary:" in run["human"]
    assert {r["type"] for r in run["rules"]} >= {"tag-conformance", "implementation-locks"}


def test_check_options_are_validated_and_shown(
    client: TestClient, demo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pid = _register(client, demo)
    monkeypatch.chdir(demo)
    bad = client.post(f"/api/projects/{pid}/check", json={"fail_on": "maybe"})
    assert bad.status_code == 400
    no_reason = client.post(f"/api/projects/{pid}/check", json={"bypass_locks": True})
    assert no_reason.status_code == 400 and "reason" in no_reason.text

    # Change the body of the locked `Receipt.formatted`: the lock fails.
    billing = demo / "orders" / "billing.py"
    text = billing.read_text(encoding="utf-8")
    at = text.index(":\n", text.index("def formatted(self)")) + 2
    billing.write_text(text[:at] + "        changed = True\n" + text[at:], encoding="utf-8")
    run = client.post(
        f"/api/projects/{pid}/check", json={"bypass_locks": True, "bypass_reason": "hotfix 12"}
    ).json()
    assert run["report"]["summary"]["bypassed"] is True
    assert run["report"]["summary"]["bypass_reason"] == "hotfix 12"
    assert [v["qualified_name"] for v in run["report"]["bypassed"]] == ["orders.Receipt.formatted"]
    assert "--bypass-locks" in run["command"] and "hotfix 12" in run["command"]

    # A model is not source code: the CLI has no such run, and nothing is acceptable.
    model = client.post(f"/api/projects/{pid}/check", json={"subject": "reference"}).json()
    assert model["command"] == "" and model["acceptable"] is False
    skipped = {s["rule_id"] for s in model["report"]["skipped"]}
    assert {r["id"] for r in model["rules"] if r["type"] == "tag-conformance"} <= skipped
