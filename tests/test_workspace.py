"""The viewer's local workspace: recent paths and auto-saved views in `.cdec_cache/`."""

from __future__ import annotations

import itertools
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from code_constraints.cli.__main__ import app as cli_app
from code_constraints.cli.detect import detect_language
from code_constraints.web import app as web_app
from code_constraints.web import workspace

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _clock(monkeypatch):
    """A clock that moves one second per call, so "most recently used" is exact."""
    ticks = itertools.count(1_000)
    monkeypatch.setattr(workspace, "_now", lambda: float(next(ticks)))


@pytest.fixture
def cache(tmp_path: Path) -> Path:
    return tmp_path / ".cdec_cache"


@pytest.fixture
def client(cache: Path, monkeypatch) -> TestClient:
    monkeypatch.setattr(web_app, "CACHE_ROOT", cache)
    return TestClient(web_app.app)


# ---------- the store ----------

def test_ensure_cache_creates_a_folder_that_ignores_itself(cache: Path):
    workspace.ensure_cache(cache)
    assert cache.is_dir()
    assert "*" in (cache / ".gitignore").read_text(encoding="utf-8").split()
    # A second start keeps what the user wrote there.
    (cache / ".gitignore").write_text("mine\n", encoding="utf-8")
    workspace.ensure_cache(cache)
    assert (cache / ".gitignore").read_text(encoding="utf-8") == "mine\n"


def test_recent_paths_are_most_recent_first_and_have_no_duplicates(cache: Path):
    workspace.touch_recent(cache, "aaa", "/src/a", "python")
    workspace.touch_recent(cache, "bbb", "/src/b", "csharp")
    workspace.touch_recent(cache, "aaa", "/src/a", "python")
    assert [e["id"] for e in workspace.list_recent(cache)] == ["aaa", "bbb"]

    workspace.forget_recent(cache, "aaa")
    assert [e["id"] for e in workspace.list_recent(cache)] == ["bbb"]


def test_recent_list_is_capped(cache: Path):
    for i in range(workspace.MAX_RECENT + 5):
        workspace.touch_recent(cache, f"p{i}", f"/src/{i}", "python")
    recent = workspace.list_recent(cache)
    assert len(recent) == workspace.MAX_RECENT
    assert recent[0]["id"] == f"p{workspace.MAX_RECENT + 4}"


def test_untitled_names_increment(cache: Path):
    names = [workspace.create_view(cache, "proj")["name"] for _ in range(3)]
    assert names == ["Untitled 1", "Untitled 2", "Untitled 3"]


def test_untitled_number_is_not_reused_below_the_highest(cache: Path):
    views = [workspace.create_view(cache, "proj") for _ in range(3)]
    workspace.delete_view(cache, "proj", views[1]["id"])  # Untitled 2
    assert workspace.create_view(cache, "proj")["name"] == "Untitled 4"
    # A view the user named does not take part in the count.
    workspace.create_view(cache, "proj", "Untitled plan")
    assert workspace.next_untitled(["Billing", "untitled 9", "Untitled 2"]) == "Untitled 3"


def test_views_are_listed_most_recently_used_first(cache: Path):
    a = workspace.create_view(cache, "proj")
    b = workspace.create_view(cache, "proj")
    assert [v["id"] for v in workspace.list_views(cache, "proj")] == [b["id"], a["id"]]

    workspace.update_view(cache, "proj", a["id"])  # opened again
    listed = workspace.list_views(cache, "proj")
    assert [v["id"] for v in listed] == [a["id"], b["id"]]
    assert "state" not in listed[0]


def test_update_view_saves_state_and_name(cache: Path):
    view = workspace.create_view(cache, "proj")
    state = {"visibleClassIds": ["class-1"], "nodePositions": {"class-1": {"x": 1, "y": 2}}}
    workspace.update_view(cache, "proj", view["id"], state=state)
    workspace.update_view(cache, "proj", view["id"], name="  Billing   slice ")

    saved = workspace.read_view(cache, "proj", view["id"])
    assert saved["name"] == "Billing slice"
    assert saved["state"] == state  # a rename keeps the state


def test_views_belong_to_one_path(cache: Path):
    workspace.create_view(cache, "proj-a")
    assert workspace.list_views(cache, "proj-b") == []
    assert workspace.create_view(cache, "proj-b")["name"] == "Untitled 1"


@pytest.mark.parametrize("bad", ["", "   ", "x" * (workspace.MAX_NAME_LENGTH + 1)])
def test_bad_view_names_are_refused(cache: Path, bad: str):
    view = workspace.create_view(cache, "proj")
    with pytest.raises(workspace.WorkspaceError):
        workspace.update_view(cache, "proj", view["id"], name=bad)


@pytest.mark.parametrize("bad", ["../../etc/passwd", "..", "ABCDEF012345", "a" * 11, ""])
def test_a_view_id_cannot_leave_the_views_folder(cache: Path, bad: str):
    with pytest.raises(workspace.WorkspaceError):
        workspace.read_view(cache, "proj", bad)


def test_a_damaged_file_does_not_stop_the_listing(cache: Path):
    good = workspace.create_view(cache, "proj")
    (cache / "proj" / "views" / "0123456789ab.json").write_text("{ not json", encoding="utf-8")
    (cache / workspace.RECENT_FILENAME).write_text("{ not json", encoding="utf-8")
    assert [v["id"] for v in workspace.list_views(cache, "proj")] == [good["id"]]
    assert workspace.list_recent(cache) == []


# ---------- the API ----------

def _register(client: TestClient, path: Path, lang: str = "python") -> str:
    r = client.post("/api/projects", json={"path": str(path), "lang": lang})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_api_view_round_trip(client: TestClient, cache: Path):
    pid = _register(client, FIXTURES / "python_demo")
    assert client.get("/api/workspace").json() == []

    first = client.post(f"/api/projects/{pid}/workspace/views").json()
    second = client.post(f"/api/projects/{pid}/workspace/views").json()
    assert (first["name"], second["name"]) == ("Untitled 1", "Untitled 2")
    assert first["state"] is None

    state = {"visibleClassIds": None, "nodePositions": {}}
    r = client.put(
        f"/api/projects/{pid}/workspace/views/{first['id']}",
        json={"state": state, "name": "Orders"},
    )
    assert r.status_code == 200, r.text

    # The path is in the recent list, with its views most recently used first.
    (recent,) = client.get("/api/workspace").json()
    assert recent["id"] == pid and recent["lang"] == "python" and recent["exists"] is True
    assert [v["name"] for v in recent["views"]] == ["Orders", "Untitled 2"]

    opened = client.post(f"/api/projects/{pid}/workspace/views/{second['id']}/open").json()
    assert opened["state"] is None
    assert [v["name"] for v in client.get(f"/api/projects/{pid}/workspace/views").json()] == [
        "Untitled 2",
        "Orders",
    ]
    assert client.post(f"/api/projects/{pid}/workspace/views/{first['id']}/open").json()["state"] == state

    assert client.delete(f"/api/projects/{pid}/workspace/views/{first['id']}").status_code == 204
    assert client.post(f"/api/projects/{pid}/workspace/views/{first['id']}/open").status_code == 404
    # The views are files under the cache folder of the server.
    assert len(list((cache / pid / "views").glob("*.json"))) == 1


def test_api_views_survive_a_server_restart(client: TestClient):
    """The registry is in memory. The recent list and the views are on disk."""
    pid = _register(client, FIXTURES / "python_demo")
    client.post(f"/api/projects/{pid}/workspace/views")
    web_app._registry._projects.clear()

    (recent,) = client.get("/api/workspace").json()
    assert [v["name"] for v in recent["views"]] == ["Untitled 1"]
    # The home page registers the path again before it opens a view.
    assert _register(client, Path(recent["path"]), recent["lang"]) == pid
    assert client.post(f"/api/projects/{pid}/workspace/views").json()["name"] == "Untitled 2"


def test_api_recent_touch_and_forget(client: TestClient, tmp_path: Path):
    a = _register(client, FIXTURES / "python_demo")
    b = _register(client, FIXTURES / "csharp_demo", "csharp")
    for pid in (a, b, a):
        assert client.post(f"/api/workspace/recent/{pid}").status_code == 204
    assert [e["id"] for e in client.get("/api/workspace").json()] == [a, b]

    assert client.delete(f"/api/workspace/recent/{a}").status_code == 204
    assert [e["id"] for e in client.get("/api/workspace").json()] == [b]
    assert client.post("/api/workspace/recent/nosuchproject").status_code == 404


def test_api_refuses_bad_view_requests(client: TestClient):
    pid = _register(client, FIXTURES / "python_demo")
    view = client.post(f"/api/projects/{pid}/workspace/views").json()
    url = f"/api/projects/{pid}/workspace/views"
    assert client.put(f"{url}/{view['id']}", json={"name": "   "}).status_code == 400
    assert client.put(f"{url}/not-an-id", json={"name": "x"}).status_code == 400
    assert client.put(f"{url}/0123456789ab", json={"name": "x"}).status_code == 404
    assert client.post("/api/projects/nosuchproject/workspace/views").status_code == 404


def test_api_detects_the_language_of_a_path(client: TestClient, tmp_path: Path):
    def detect(path) -> dict:
        r = client.get("/api/detect-language", params={"path": str(path)})
        assert r.status_code == 200, r.text
        return r.json()

    assert detect(FIXTURES / "python_demo") == {"lang": "python", "is_dir": True}
    assert detect(FIXTURES / "csharp_demo") == {"lang": "csharp", "is_dir": True}
    assert detect(tmp_path) == {"lang": None, "is_dir": True}  # nothing to recognise
    # A path the user is still typing is not an error.
    assert detect(tmp_path / "does" / "not" / "exist") == {"lang": None, "is_dir": False}
    assert detect("") == {"lang": None, "is_dir": False}


# ---------- language detection budget ----------

def test_detection_stops_at_the_file_budget(tmp_path: Path):
    for i in range(5):
        (tmp_path / f"a{i}.py").write_text("", encoding="utf-8")
    deep = tmp_path / "deep"
    deep.mkdir()
    for i in range(50):
        (deep / f"b{i}.cs").write_text("", encoding="utf-8")

    assert detect_language(tmp_path) == "csharp"
    # The budget is used up by the top folder, so `deep` is not read.
    assert detect_language(tmp_path, max_files=5) == "python"


# ---------- the CLI ----------

def test_ui_creates_the_cache_folder_at_start(tmp_path: Path, monkeypatch):
    cache = tmp_path / ".cdec_cache"
    monkeypatch.setattr(web_app, "CACHE_ROOT", cache)
    monkeypatch.setattr("uvicorn.run", lambda *a, **k: None)

    result = CliRunner().invoke(cli_app, ["ui", "--no-browser"])
    assert result.exit_code == 0, result.output
    assert cache.is_dir()
    assert (cache / ".gitignore").is_file()
