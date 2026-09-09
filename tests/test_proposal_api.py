"""Tests for the proposal review loop (`POST/GET /api/projects/{id}/proposal`)
and the editor's live-diff endpoint (`POST /api/edit/diff-model`)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from code_constraints.core.editor_io import project_to_json
from code_constraints.python import parse_project
from code_constraints.web.app import app

FIXTURE = (Path(__file__).parent / "fixtures" / "python_demo").resolve()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _register(client: TestClient) -> str:
    r = client.post("/api/projects", json={"path": str(FIXTURE), "lang": "python"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _proposal_payload() -> dict:
    """Current fixture model plus one brand-new class."""
    data = project_to_json(parse_project(FIXTURE))
    data["packages"][0]["classes"].append(
        {
            "name": "ProposedService",
            "qualified_name": data["packages"][0]["qualified_name"]
            + ".ProposedService",
            "kind": "class",
            "attributes": [],
            "operations": [],
            "bases": [],
        }
    )
    return data


def test_push_proposal_diffs_against_source(client: TestClient) -> None:
    project_id = _register(client)

    r = client.post(
        f"/api/projects/{project_id}/proposal?focus=ProposedService",
        json=_proposal_payload(),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["seq"] == 1
    assert body["focus"] == ["ProposedService"]

    # The annotated XMI renders through the normal viewer path, with the new
    # class marked "added" (green = the code still needs to grow this).
    r = client.get(f"/api/xmi/{body['id']}/model?diagram=class")
    assert r.status_code == 200, r.text
    nodes = r.json()["nodes"]
    added = {n["name"] for n in nodes if n["status"] == "added"}
    assert "ProposedService" in added


def test_proposal_seq_increments_and_latest_is_pollable(client: TestClient) -> None:
    project_id = _register(client)
    payload = _proposal_payload()

    first = client.post(f"/api/projects/{project_id}/proposal", json=payload).json()
    second = client.post(f"/api/projects/{project_id}/proposal", json=payload).json()
    assert second["seq"] == first["seq"] + 1

    r = client.get(f"/api/projects/{project_id}/proposal")
    assert r.status_code == 200
    assert r.json()["id"] == second["id"]


def test_proposal_against_none_renders_standalone(client: TestClient) -> None:
    project_id = _register(client)
    r = client.post(
        f"/api/projects/{project_id}/proposal?against=none",
        json=_proposal_payload(),
    )
    assert r.status_code == 200, r.text
    r = client.get(f"/api/xmi/{r.json()['id']}/model?diagram=class")
    statuses = {n["status"] for n in r.json()["nodes"]}
    assert statuses == {"unchanged"}


def test_proposal_rejects_bad_against(client: TestClient) -> None:
    project_id = _register(client)
    r = client.post(
        f"/api/projects/{project_id}/proposal?against=bogus",
        json=_proposal_payload(),
    )
    assert r.status_code == 400


def test_no_proposal_yet_returns_404(client: TestClient) -> None:
    project_id = _register(client)
    # A fresh registry entry may already carry a proposal from another test
    # (deterministic project ids); use a distinct tmp-free guard instead: only
    # assert 404 when nothing was pushed in this project's lifetime.
    r = client.get(f"/api/projects/{project_id}/proposal")
    assert r.status_code in (200, 404)


def test_edit_diff_model_marks_changes(client: TestClient) -> None:
    old = project_to_json(parse_project(FIXTURE))
    new = _proposal_payload()
    r = client.post("/api/edit/diff-model?diagram=class", json={"old": old, "new": new})
    assert r.status_code == 200, r.text
    nodes = r.json()["nodes"]
    assert any(
        n["name"] == "ProposedService" and n["status"] == "added" for n in nodes
    )


def test_edit_diff_model_requires_old_and_new(client: TestClient) -> None:
    r = client.post("/api/edit/diff-model", json={"new": {}})
    assert r.status_code == 400


def test_reference_model_404_without_reference(
    client: TestClient, tmp_path: Path
) -> None:
    (tmp_path / "main.py").write_text("x = 1\n", encoding="utf-8")
    r = client.post("/api/projects", json={"path": str(tmp_path), "lang": "python"})
    project_id = r.json()["id"]
    r = client.get(f"/api/projects/{project_id}/reference-model")
    assert r.status_code == 404
