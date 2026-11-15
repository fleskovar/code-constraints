"""The tasks behind the wizards of the web app: edit and remove a rule,
withdraw and prune exceptions, compare with the goal and close it, locks, tag
snippets, the shim, the CI scripts."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from code_constraints import journal
from code_constraints.cli.scaffold import init_cdec_config
from code_constraints.core import rulesdoc
from code_constraints.core.tag_syntax import tag_snippet
from code_constraints.web.app import app

FIXTURE = (Path(__file__).parent / "fixtures" / "python_demo").resolve()
DEMO = (Path(__file__).parent.parent / "examples" / "python_demo").resolve()

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


# ---------- the `rules:` list ----------

def test_replace_and_remove_touch_one_entry(project: Path) -> None:
    path = project / ".cdec" / "rules.yaml"
    for rule_id in ("a", "b", "c"):
        rulesdoc.append_rule(path, {"id": rule_id, "type": "no-new-classes"})
    text = path.read_text(encoding="utf-8").replace("  - id: c\n", "  # why c exists\n  - id: c\n")
    path.write_text(text, encoding="utf-8")

    rulesdoc.replace_rule(path, "b", {"id": "b2", "type": "max-class-fanout", "limit": 4})
    rulesdoc.remove_rule(path, "a")
    assert [r["id"] for r in rulesdoc.load_document(path)["rules"]] == ["b2", "c"]
    after = path.read_text(encoding="utf-8")
    assert "# why c exists\n  - id: c" in after and "# Examples" in after

    rulesdoc.remove_rule(path, "b2")
    rulesdoc.remove_rule(path, "c")
    assert rulesdoc.load_document(path)["rules"] == []
    rulesdoc.append_rule(path, {"id": "again", "type": "no-new-classes"})  # still editable


# ---------- tag syntax: the forms that docs/ and the bundle give ----------

@pytest.mark.parametrize(
    ("lang", "tag", "values", "expected"),
    [
        ("python", "sealed", {}, "@sealed"),
        ("python", "layer", {"name": "domain"}, '@layer("domain")'),
        ("python", "factory", {"creates": "Receipt"}, '@factory(creates=["Receipt"])'),
        ("python", "locked", {"reason": "r", "owner": "o"}, '@locked(reason="r", owner="o")'),
        ("csharp", "layer", {"name": "domain"}, '[Layer("domain")]'),
        ("csharp", "no-instantiation", {"allow": "A, B"},
         '[NoInstantiation(Allow = new[] { "A", "B" })]'),
        ("csharp", "locked", {"reason": "r"}, '[Locked(Reason = "r")]'),
        ("julia", "layer", {"name": "domain"}, '@layer "domain"'),
        ("julia", "factory", {"creates": "Receipt"}, '@factory creates=["Receipt"]'),
        ("lua", "factory", {"creates": "Receipt"}, '---@cdec factory(creates = {"Receipt"})'),
        ("odin", "no-instantiation", {"allow": "AuditEntry"},
         '//@cdec no_instantiation(allow = ["AuditEntry"])'),
        ("odin", "sealed", {}, "//@cdec sealed"),
    ],
)
def test_tag_snippet(lang: str, tag: str, values: dict[str, str], expected: str) -> None:
    assert tag_snippet(tag, lang, values)["tag"] == expected


def test_a_python_tag_names_its_import() -> None:
    assert tag_snippet("sealed", "python")["import"] == "from cdec_rules import sealed"
    with pytest.raises(ValueError):
        tag_snippet("sealed", "typescript")


# ---------- the web endpoints ----------

def test_a_rule_is_edited_and_removed(client: TestClient, project: Path) -> None:
    pid = _register(client, project)
    assert client.post(f"/api/projects/{pid}/rules", json={"entry": FANOUT}).status_code == 200
    both = client.post("/api/rule-entry", json={"entry": FANOUT}).json()
    assert both["yaml"].startswith("- id: fanout") and both["entry"] == FANOUT

    r = client.put(f"/api/projects/{pid}/rules/fanout/entry", json={"entry": {**FANOUT, "limit": 99}})
    assert r.status_code == 204, r.text
    (rule,) = client.get(f"/api/projects/{pid}/rules").json()["rules"]
    assert rule["entry"]["limit"] == 99 and rule["open"] == 0

    # An entry that the loader refuses does not reach the file.
    bad = client.put(f"/api/projects/{pid}/rules/fanout/entry", json={"entry": {"id": "x", "type": "nope"}})
    assert bad.status_code == 400

    assert client.delete(f"/api/projects/{pid}/rules/fanout").status_code == 204
    assert client.get(f"/api/projects/{pid}/rules").json()["rules"] == []


def test_exceptions_are_withdrawn_and_stale_ones_pruned(client: TestClient, project: Path) -> None:
    pid = _register(client, project)
    client.post(f"/api/projects/{pid}/rules", json={"entry": FANOUT, "accept_existing": True})
    overview = client.get(f"/api/projects/{pid}/rules").json()
    keys = [e["key"] for e in overview["exceptions"]]
    assert keys and not any(e["stale"] for e in overview["exceptions"])

    r = client.request("DELETE", f"/api/projects/{pid}/exceptions", json={"keys": keys})
    assert r.json() == {"removed": len(keys)}
    assert client.get(f"/api/projects/{pid}/rules").json()["rules"][0]["open"] == len(keys)
    client.post(f"/api/projects/{pid}/exceptions", json={"keys": keys, "reason": "again"})

    # The rule gets a high limit: no issue is left, so every exception is stale.
    client.put(f"/api/projects/{pid}/rules/fanout/entry", json={"entry": {**FANOUT, "limit": 99}})
    stale = client.get(f"/api/projects/{pid}/rules").json()["exceptions"]
    assert stale and all(e["stale"] for e in stale)
    assert client.post(f"/api/projects/{pid}/exceptions/prune").json() == {"removed": len(stale)}
    assert client.get(f"/api/projects/{pid}/rules").json()["exceptions"] == []


def test_an_unknown_git_ref_is_a_client_error(client: TestClient, project: Path) -> None:
    pid = _register(client, project)
    assert client.get(f"/api/projects/{pid}/rules?base_ref=no-such-ref").status_code == 400


def test_the_code_is_compared_with_the_goal_and_the_goal_is_closed(
    client: TestClient, project: Path
) -> None:
    pid = _register(client, project)
    cfg = project / ".cdec"
    # The goal is the code of today. Then the code grows a class.
    body = (cfg / "reference.xmi").read_bytes()
    client.put(f"/api/projects/{pid}/reference?kind=goal&title=Target", content=body)
    (project / "extra.py").write_text("class Extra:\n    pass\n", encoding="utf-8")

    frame = client.post(f"/api/projects/{pid}/reference/compare")
    assert frame.status_code == 200, frame.text
    changes = client.get(f"/api/xmi/{frame.json()['id']}/changes").json()
    # The code is the old side: a class that is only in the code shows as removed.
    assert [(c["classQname"].split(".")[-1], c["kind"]) for c in changes] == [("Extra", "removed")]

    r = client.post(f"/api/projects/{pid}/reference/snapshot", json={"title": "Done", "note": "ok"})
    assert r.status_code == 200, r.text
    assert "Extra" in (cfg / "reference.xmi").read_text(encoding="utf-8")
    history = journal.entries(cfg)
    assert journal.open_goal(history) is None and history[-1].title == "Done"


def test_locks_are_listed_recorded_and_rebaselined(client: TestClient, tmp_path: Path) -> None:
    root = tmp_path / "demo"
    shutil.copytree(DEMO, root, ignore=shutil.ignore_patterns("__pycache__"))
    pid = _register(client, root)

    overview = client.get(f"/api/projects/{pid}/locks").json()
    assert overview["rule"] and overview["supported"]
    states = {t["target"]: t["state"] for t in overview["targets"]}
    assert states == {"orders.Receipt.formatted": "ok"}

    source = root / "orders" / "billing.py"
    text = source.read_text(encoding="utf-8")
    marker = "def formatted(self)"
    head, tail = text.split(marker, 1)
    body_start = tail.index(":\n") + 2
    source.write_text(
        head + marker + tail[:body_start] + "        changed = True\n" + tail[body_start:],
        encoding="utf-8",
    )
    (target,) = client.get(f"/api/projects/{pid}/locks").json()["targets"]
    assert target["state"] == "changed"

    # The safe form adds locks only. It does not accept the change.
    assert client.post(f"/api/projects/{pid}/locks", json={}).status_code == 200
    assert client.get(f"/api/projects/{pid}/locks").json()["targets"][0]["state"] == "changed"
    # `force` needs the names of the elements.
    assert client.post(f"/api/projects/{pid}/locks", json={"force": True}).status_code == 400

    r = client.post(
        f"/api/projects/{pid}/locks", json={"force": True, "targets": ["orders.Receipt.formatted"]}
    )
    assert r.status_code == 200, r.text
    assert client.get(f"/api/projects/{pid}/locks").json()["targets"][0]["state"] == "ok"


def test_the_shim_and_the_ci_scripts_are_written(client: TestClient, project: Path) -> None:
    pid = _register(client, project)
    status = client.get(f"/api/projects/{pid}/journey").json()
    assert (status["shim"], status["shim_present"]) == ("cdec_rules.py", False)

    assert client.post(f"/api/projects/{pid}/shims").status_code == 200
    assert (project / "cdec_rules.py").is_file()
    assert client.get(f"/api/projects/{pid}/journey").json()["shim_present"] is True

    written = client.post(f"/api/projects/{pid}/ci-scripts").json()["written"]
    assert sorted(Path(p).name for p in written) == ["cdec-ci.bat", "cdec-ci.sh"]

    tags = client.get("/api/tags?lang=python").json()
    assert tags["supported"] and {t["id"] for t in tags["tags"]} >= {"sealed", "layer", "locked"}
    assert client.get("/api/tags?lang=typescript").json()["supported"] is False
    snippet = client.post(
        "/api/tags/snippet", json={"lang": "python", "tag": "layer", "values": {"name": "domain"}}
    ).json()
    assert snippet == {"tag": '@layer("domain")', "import": "from cdec_rules import layer"}
