"""Integration tests for the FastAPI backend (no rendering — that requires Java)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from code_constraints.web.app import app

FIXTURE = (Path(__file__).parent / "fixtures" / "python_demo").resolve()
MVC_DEMO = (Path(__file__).parent.parent / "examples" / "csharp_mvc_demo").resolve()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_layer_dependencies_from_rules_yaml(client: TestClient) -> None:
    r = client.post("/api/projects", json={"path": str(MVC_DEMO), "lang": "csharp"})
    assert r.status_code == 200, r.text
    project_id = r.json()["id"]

    r = client.get(f"/api/projects/{project_id}/layers")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["allow"] == {
        "model": [],
        "view": ["model"],
        "controller": ["model", "view"],
    }
    assert body["source"].replace("\\", "/").endswith(".cdec/rules.yaml")


def test_layer_dependencies_absent_returns_empty(
    client: TestClient, tmp_path: Path
) -> None:
    # A directory with no .cdec/rules.yaml anywhere up the tree -> empty matrix.
    (tmp_path / "main.py").write_text("x = 1\n", encoding="utf-8")
    r = client.post("/api/projects", json={"path": str(tmp_path), "lang": "python"})
    project_id = r.json()["id"]
    r = client.get(f"/api/projects/{project_id}/layers")
    assert r.status_code == 200, r.text
    assert r.json() == {"allow": {}, "source": None}


def test_register_project_and_parse(client: TestClient) -> None:
    r = client.post("/api/projects", json={"path": str(FIXTURE), "lang": "python"})
    assert r.status_code == 200, r.text
    project_id = r.json()["id"]

    r = client.post(f"/api/projects/{project_id}/parse")
    assert r.status_code == 200, r.text
    xmi_id = r.json()["id"]

    r = client.get(f"/api/xmi/{xmi_id}/diagrams")
    assert r.status_code == 200
    body = r.json()
    assert body["classes"] is True
    assert body["packages"] is True
    assert "dog_speak" in body["activities"]
    assert "checkout_flow" in body["sequences"]


def test_unknown_project_returns_404(client: TestClient) -> None:
    r = client.get("/api/projects/does-not-exist/refs")
    assert r.status_code == 404


def test_register_rejects_bad_lang(client: TestClient) -> None:
    r = client.post("/api/projects", json={"path": str(FIXTURE), "lang": "ruby"})
    assert r.status_code == 400


def test_git_info_for_repo_path(client: TestClient) -> None:
    """The fixtures live inside this repo, so git-info should report is_git."""
    r = client.post("/api/projects", json={"path": str(FIXTURE), "lang": "python"})
    project_id = r.json()["id"]
    r = client.get(f"/api/projects/{project_id}/git-info")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_git"] is True
    assert body["head_sha"] and len(body["head_sha"]) >= 7
    assert body["head_short"] == body["head_sha"][:10]
    # The repo has multiple commits, so a parent must exist.
    assert body["parent_sha"]
    assert isinstance(body["is_dirty"], bool)


def test_git_info_for_non_repo_path(client: TestClient, tmp_path) -> None:
    bare = tmp_path / "not-a-repo"
    bare.mkdir()
    r = client.post("/api/projects", json={"path": str(bare), "lang": "python"})
    project_id = r.json()["id"]
    r = client.get(f"/api/projects/{project_id}/git-info")
    assert r.status_code == 200
    body = r.json()
    assert body["is_git"] is False
    assert body["head_sha"] is None
    assert body["parent_sha"] is None


def test_diff_with_subpath_missing_on_one_side_treats_as_empty(
    client: TestClient,
) -> None:
    """Quick-diff against HEAD~1 must not 500 when the project subpath was
    only added at HEAD. The missing side is parsed as an empty Project so the
    diff renders everything as ADDED."""
    # Use the examples/python_demo path which was added in a recent commit; at
    # earlier commits it didn't exist.
    demo = (Path(__file__).parent.parent / "examples" / "python_demo").resolve()
    if not demo.exists():
        pytest.skip("examples/python_demo missing")
    r = client.post("/api/projects", json={"path": str(demo), "lang": "python"})
    project_id = r.json()["id"]
    r = client.get(f"/api/projects/{project_id}/git-info")
    info = r.json()
    if not info["is_git"] or not info["parent_sha"]:
        pytest.skip("not in a git repo with a parent commit")
    # A shallow clone names HEAD~1 but has none of its objects, so there is no
    # older tree to diff against. That is a 400 from the endpoint, tested
    # separately; this test is about the subpath case.
    shallow = subprocess.run(
        ["git", "-C", info["repo_root"], "rev-parse", "--is-shallow-repository"],
        capture_output=True, text=True, check=False,  # a failure just means "not shallow"
    ).stdout.strip()
    if shallow == "true":
        pytest.skip("shallow clone: HEAD~1 trees are not available")
    subpath = info["subpath"] or ""
    r = client.post(
        f"/api/projects/{project_id}/diff",
        json={"old_ref": "HEAD~1", "new_ref": "HEAD", "subpath": subpath},
    )
    # Either both sides parse (the dir existed both places) or one side was
    # empty — the endpoint must NOT return 500 either way.
    assert r.status_code == 200, r.text


def test_diff_two_uploaded_xmi_files(client: TestClient) -> None:
    """POST /api/xmi/diff accepts two XMIs and returns an annotated XMI id."""
    # Produce two XMIs by parsing the same fixture; the diff should report
    # everything unchanged.
    r = client.post("/api/projects", json={"path": str(FIXTURE), "lang": "python"})
    pid = r.json()["id"]
    xmi_a = client.post(f"/api/projects/{pid}/parse").json()["id"]
    xmi_b = client.post(f"/api/projects/{pid}/parse").json()["id"]

    # Fetch the XMI source bytes
    a_bytes = client.get(f"/api/xmi/{xmi_a}/source").content
    b_bytes = client.get(f"/api/xmi/{xmi_b}/source").content

    r = client.post(
        "/api/xmi/diff",
        files={
            "old_xmi": ("old.xmi", a_bytes, "application/xml"),
            "new_xmi": ("new.xmi", b_bytes, "application/xml"),
        },
    )
    assert r.status_code == 200, r.text
    diff_xmi_id = r.json()["id"]
    diff_project_id = r.json()["project_id"]
    # The result is browsable via the existing diagram endpoints.
    r = client.get(f"/api/xmi/{diff_xmi_id}/diagrams")
    assert r.status_code == 200
    # An empty `changes` list (parses are identical → no diff content)
    r = client.get(f"/api/xmi/{diff_xmi_id}/changes")
    assert r.status_code == 200
    assert r.json() == []
    # Synthetic project resolves
    r = client.get("/api/projects")
    paths = [p["path"] for p in r.json() if p["id"] == diff_project_id]
    assert paths and paths[0].startswith("uploaded:")


def test_diff_source_vs_xmi(client: TestClient) -> None:
    """POST /api/projects/diff-vs-xmi parses source and diffs vs an XMI."""
    # Build a reference XMI from the fixture
    r = client.post("/api/projects", json={"path": str(FIXTURE), "lang": "python"})
    pid = r.json()["id"]
    ref_xmi_id = client.post(f"/api/projects/{pid}/parse").json()["id"]
    ref_bytes = client.get(f"/api/xmi/{ref_xmi_id}/source").content

    # Now diff the same source against itself: should be all unchanged.
    r = client.post(
        "/api/projects/diff-vs-xmi",
        files={"reference_xmi": ("ref.xmi", ref_bytes, "application/xml")},
        data={"path": str(FIXTURE), "lang": "python"},
    )
    assert r.status_code == 200, r.text
    diff_xmi_id = r.json()["id"]
    assert client.get(f"/api/xmi/{diff_xmi_id}/changes").json() == []


def test_diff_source_vs_xmi_rejects_cross_language(client: TestClient) -> None:
    examples = (Path(__file__).parent.parent / "examples").resolve()
    py = examples / "python_demo"
    cs = examples / "csharp_demo"
    if not (py.exists() and cs.exists()):
        pytest.skip("examples/ codebases missing")
    # Build a CSHARP reference XMI…
    cs_pid = client.post(
        "/api/projects", json={"path": str(cs), "lang": "csharp"}
    ).json()["id"]
    cs_xmi = client.post(f"/api/projects/{cs_pid}/parse").json()["id"]
    cs_bytes = client.get(f"/api/xmi/{cs_xmi}/source").content
    # …and ask to diff it against a PYTHON source tree.
    r = client.post(
        "/api/projects/diff-vs-xmi",
        files={"reference_xmi": ("cs.xmi", cs_bytes, "application/xml")},
        data={"path": str(py), "lang": "python"},
    )
    assert r.status_code == 400
    assert "languages" in r.json()["detail"]


def test_diff_source_vs_xmi_bad_path(client: TestClient, tmp_path) -> None:
    # A reference XMI we can use
    r = client.post("/api/projects", json={"path": str(FIXTURE), "lang": "python"})
    pid = r.json()["id"]
    xmi = client.post(f"/api/projects/{pid}/parse").json()["id"]
    ref_bytes = client.get(f"/api/xmi/{xmi}/source").content
    r = client.post(
        "/api/projects/diff-vs-xmi",
        files={"reference_xmi": ("ref.xmi", ref_bytes, "application/xml")},
        data={"path": str(tmp_path / "does-not-exist"), "lang": "python"},
    )
    assert r.status_code == 400


def test_diff_xmi_rejects_cross_language(client: TestClient, tmp_path) -> None:
    """Same endpoint rejects two XMIs declaring different source languages."""
    # Build two distinct projects, one python + one csharp fixture (the demo
    # tree under examples/).
    examples = (Path(__file__).parent.parent / "examples").resolve()
    py = examples / "python_demo"
    cs = examples / "csharp_demo"
    if not (py.exists() and cs.exists()):
        pytest.skip("examples/ codebases missing")

    # Register and parse each.
    py_pid = client.post(
        "/api/projects", json={"path": str(py), "lang": "python"}
    ).json()["id"]
    cs_pid = client.post(
        "/api/projects", json={"path": str(cs), "lang": "csharp"}
    ).json()["id"]
    py_xmi = client.post(f"/api/projects/{py_pid}/parse").json()["id"]
    cs_xmi = client.post(f"/api/projects/{cs_pid}/parse").json()["id"]
    py_bytes = client.get(f"/api/xmi/{py_xmi}/source").content
    cs_bytes = client.get(f"/api/xmi/{cs_xmi}/source").content

    r = client.post(
        "/api/xmi/diff",
        files={
            "old_xmi": ("py.xmi", py_bytes, "application/xml"),
            "new_xmi": ("cs.xmi", cs_bytes, "application/xml"),
        },
    )
    assert r.status_code == 400
    assert "cannot diff across languages" in r.json()["detail"]


def test_edit_model_matches_view_model(client: TestClient) -> None:
    """The editor's /api/edit/model must produce the same graph as view mode's
    /api/xmi/{id}/model. This guards against the editor silently dropping
    attribute-derived associations (which it did at first, when it had its
    own TS graph builder)."""
    cs_demo = Path(__file__).resolve().parents[1] / "examples" / "csharp_demo"
    pid = client.post(
        "/api/projects", json={"path": str(cs_demo), "lang": "csharp"}
    ).json()["id"]
    xmi_id = client.post(f"/api/projects/{pid}/parse").json()["id"]

    # View-mode graph
    view_graph = client.get(f"/api/xmi/{xmi_id}/model?diagram=class").json()
    assert any(
        e["kind"] == "association"
        and view_graph_node_by_id(view_graph, e["source"])["name"] == "Book"
        and view_graph_node_by_id(view_graph, e["target"])["name"] == "Author"
        for e in view_graph["edges"]
    ), "view mode is missing the Book -> Author association"

    # Round-trip the same XMI through the editor's JSON shape.
    xmi_bytes = client.get(f"/api/xmi/{xmi_id}/source").content
    draft = client.post(
        "/api/edit/from-xmi",
        files={"file": ("snap.xmi", xmi_bytes, "application/xml")},
    ).json()

    edit_graph = client.post(
        "/api/edit/model?diagram=class", json=draft
    ).json()

    # Same node ids and edges as the view-mode graph.
    assert {n["id"] for n in edit_graph["nodes"]} == {
        n["id"] for n in view_graph["nodes"]
    }
    assert {(e["source"], e["target"], e["kind"]) for e in edit_graph["edges"]} == {
        (e["source"], e["target"], e["kind"]) for e in view_graph["edges"]
    }


def view_graph_node_by_id(graph: dict, node_id: str) -> dict:
    for n in graph["nodes"]:
        if n["id"] == node_id:
            return n
    raise KeyError(node_id)


VALID_VIEW = {
    "schema": "code-constraints/view@2",
    "name": "My View",
    "visible": ["billing.BillingController", "auth.UserService"],
    "positions": {"billing.BillingController": {"x": 100.0, "y": 200.0}},
}


def _register(client: TestClient, path: Path) -> str:
    r = client.post("/api/projects", json={"path": str(path), "lang": "python"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_views_list_empty(client: TestClient, tmp_path: Path) -> None:
    """List returns [] when the project has no .cdec/views/ directory."""
    (tmp_path / "main.py").write_text("x = 1\n", encoding="utf-8")
    pid = _register(client, tmp_path)
    r = client.get(f"/api/projects/{pid}/views")
    assert r.status_code == 200, r.text
    assert r.json() == []


def test_views_crud(client: TestClient, tmp_path: Path) -> None:
    """Full create → list → get → delete lifecycle."""
    (tmp_path / "main.py").write_text("x = 1\n", encoding="utf-8")
    pid = _register(client, tmp_path)

    # Save
    r = client.put(f"/api/projects/{pid}/views/my_view.json", json=VALID_VIEW)
    assert r.status_code == 204, r.text
    assert (tmp_path / ".cdec" / "views" / "my_view.json").is_file()

    # List
    r = client.get(f"/api/projects/{pid}/views")
    assert r.status_code == 200, r.text
    listings = r.json()
    assert len(listings) == 1
    assert listings[0]["filename"] == "my_view.json"
    assert listings[0]["name"] == "My View"

    # Get round-trips cleanly
    r = client.get(f"/api/projects/{pid}/views/my_view.json")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["visible"] == VALID_VIEW["visible"]

    # Delete
    r = client.delete(f"/api/projects/{pid}/views/my_view.json")
    assert r.status_code == 204, r.text
    r = client.get(f"/api/projects/{pid}/views")
    assert r.json() == []


def test_views_rejects_path_traversal(client: TestClient, tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("x = 1\n", encoding="utf-8")
    pid = _register(client, tmp_path)
    r = client.put(f"/api/projects/{pid}/views/../evil.json", json=VALID_VIEW)
    # Router normalises the path — traversal is blocked before the handler runs
    assert r.status_code in (400, 404, 405, 422)


def test_views_rejects_bad_schema(client: TestClient, tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("x = 1\n", encoding="utf-8")
    pid = _register(client, tmp_path)
    bad = {**VALID_VIEW, "schema": "code-constraints/view@1"}
    r = client.put(f"/api/projects/{pid}/views/myview.json", json=bad)
    assert r.status_code == 400, r.text


def test_views_cdec_dir_walk_up(client: TestClient, tmp_path: Path) -> None:
    """When the project sits in a subdirectory, views land in the ancestor .cdec/."""
    cdec_dir = tmp_path / ".cdec"
    cdec_dir.mkdir()
    (cdec_dir / "rules.yaml").write_text("rules: []\n", encoding="utf-8")
    subdir = tmp_path / "subproject"
    subdir.mkdir()
    (subdir / "main.py").write_text("x = 1\n", encoding="utf-8")
    pid = _register(client, subdir)

    r = client.put(f"/api/projects/{pid}/views/myview.json", json=VALID_VIEW)
    assert r.status_code == 204, r.text
    # File must land in the ancestor .cdec/, not in subproject/.cdec/
    assert (cdec_dir / "views" / "myview.json").is_file()
    assert not (subdir / ".cdec").exists()


def test_set_reference_writes_cdec_dir(client: TestClient, tmp_path: Path) -> None:
    """PUT /reference validates XMI bytes and writes .cdec/reference.xmi."""
    # Build a valid XMI by parsing the fixture.
    pid = _register(client, FIXTURE)
    xmi_id = client.post(f"/api/projects/{pid}/parse").json()["id"]
    xmi_bytes = client.get(f"/api/xmi/{xmi_id}/source").content

    # Register a throwaway project pointing at tmp_path so we don't clobber the
    # repo's real reference. (Re-uses the same XMI bytes — they only need to be
    # a valid Project, not match tmp_path's source.)
    (tmp_path / "main.py").write_text("x = 1\n", encoding="utf-8")
    target_pid = _register(client, tmp_path)

    r = client.put(
        f"/api/projects/{target_pid}/reference",
        content=xmi_bytes,
        headers={"content-type": "application/xml"},
    )
    assert r.status_code == 200, r.text
    ref = tmp_path / ".cdec" / "reference.xmi"
    assert ref.is_file()
    assert ref.read_bytes() == xmi_bytes
    assert r.json()["path"].replace("\\", "/").endswith(".cdec/reference.xmi")


def test_set_reference_rejects_invalid_xmi(client: TestClient, tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("x = 1\n", encoding="utf-8")
    pid = _register(client, tmp_path)
    r = client.put(
        f"/api/projects/{pid}/reference",
        content=b"not xml at all",
        headers={"content-type": "application/xml"},
    )
    assert r.status_code == 400, r.text
    assert not (tmp_path / ".cdec" / "reference.xmi").exists()


def test_xmi_source_download(client: TestClient) -> None:
    r = client.post("/api/projects", json={"path": str(FIXTURE), "lang": "python"})
    project_id = r.json()["id"]
    xmi_id = client.post(f"/api/projects/{project_id}/parse").json()["id"]

    r = client.get(f"/api/xmi/{xmi_id}/source")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/xml")
    assert b"<xmi:XMI" in r.content


def test_spa_mount_prefers_the_checkout_over_the_embedded_copy() -> None:
    """A stale packaged bundle must never shadow a fresh `npm run build`.

    The wheel ships the built SPA as package data at ``web/_static`` (see
    `make frontend-embed`), but a source checkout serves ``frontend/dist``.
    If the precedence flips, `make serve` silently shows the last packaged
    build and every frontend edit looks like it did not take.
    """
    from code_constraints.web import app as app_module

    checkout = Path(app_module.__file__).resolve().parents[3] / "frontend" / "dist"
    embedded = Path(app_module.__file__).resolve().parent / "_static"
    if not checkout.exists():
        pytest.skip("frontend/dist not built")

    assert app_module._frontend_dist == checkout, (
        f"SPA mount resolved to {app_module._frontend_dist}, expected the checkout "
        f"bundle at {checkout} (embedded copy present: {embedded.exists()})"
    )


def test_git_info_survives_a_shallow_clone(client: TestClient, tmp_path) -> None:
    """A shallow clone has HEAD's parent *hash* but not its object.

    `git clone --depth 1` — and every default `actions/checkout` — produces
    one. Reading the parent's message there raises, which used to 500 the
    whole endpoint. The hash must still be reported; only the subject drops.
    """
    origin = tmp_path / "origin"
    (origin / "src").mkdir(parents=True)
    subprocess.run(["git", "-C", str(origin), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(origin), "config", "user.email", "t@example.com"], check=True)
    subprocess.run(["git", "-C", str(origin), "config", "user.name", "Test"], check=True)
    for n in ("first", "second"):
        (origin / "src" / "m.py").write_text(f"class {n.title()}:\n    pass\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(origin), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(origin), "commit", "-qm", f"{n} commit"], check=True)

    shallow = tmp_path / "shallow"
    subprocess.run(
        ["git", "clone", "-q", "--depth", "1", origin.as_uri(), str(shallow)], check=True
    )
    # Guard the guard: if this clone is not actually shallow the test proves nothing.
    depth = subprocess.run(
        ["git", "-C", str(shallow), "rev-parse", "--is-shallow-repository"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    assert depth == "true", "expected a shallow clone"

    r = client.post("/api/projects", json={"path": str(shallow / "src"), "lang": "python"})
    project_id = r.json()["id"]
    r = client.get(f"/api/projects/{project_id}/git-info")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_git"] is True
    assert body["head_sha"]
    assert body["head_subject"] == "second commit"
    # The parent is referenced by HEAD, so its hash is known even though the
    # object is absent; the subject is what degrades.
    assert body["parent_sha"]
    assert body["parent_subject"] is None


def test_diff_against_unavailable_history_is_a_client_error(
    client: TestClient, tmp_path
) -> None:
    """Asking to diff a ref whose objects were never fetched is a 400, not a 500.

    Anyone running `cdec serve` inside a shallow clone hits this from the
    quick-diff card, so it has to fail with an explanation rather than a
    stack trace.
    """
    origin = tmp_path / "o"
    (origin / "src").mkdir(parents=True)
    subprocess.run(["git", "-C", str(origin), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(origin), "config", "user.email", "t@example.com"], check=True)
    subprocess.run(["git", "-C", str(origin), "config", "user.name", "Test"], check=True)
    for n in ("one", "two"):
        (origin / "src" / "m.py").write_text(f"class {n.title()}:\n    pass\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(origin), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(origin), "commit", "-qm", n], check=True)

    shallow = tmp_path / "s"
    subprocess.run(
        ["git", "clone", "-q", "--depth", "1", origin.as_uri(), str(shallow)], check=True
    )

    r = client.post("/api/projects", json={"path": str(shallow / "src"), "lang": "python"})
    project_id = r.json()["id"]
    r = client.post(
        f"/api/projects/{project_id}/diff",
        json={"old_ref": "HEAD~1", "new_ref": "HEAD", "subpath": ""},
    )

    assert r.status_code == 400, r.text
    assert "unshallow" in r.json()["detail"]
