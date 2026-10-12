"""Desktop actions of the viewer: reveal a source file, open it in an editor."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from code_constraints.web import app as web_app
from code_constraints.web import desktop

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def spawned(monkeypatch) -> list[list[str]]:
    """Record every program the code starts. Start none."""
    calls: list[list[str]] = []
    monkeypatch.setattr(subprocess, "Popen", lambda argv, **kw: calls.append(list(argv)))
    return calls


@pytest.fixture
def started(monkeypatch) -> list[tuple[str, str]]:
    """Record every `os.startfile` call (Windows "open" / "edit")."""
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        os, "startfile", lambda path, verb="open": calls.append((path, verb)), raising=False
    )
    return calls


# ---------- which file ----------

def test_resolve_source_file_stays_inside_the_project(tmp_path: Path):
    root = tmp_path / "proj"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "a.py").write_text("", encoding="utf-8")
    (tmp_path / "secret.py").write_text("", encoding="utf-8")

    assert desktop.resolve_source_file(root, "pkg/a.py") == (root / "pkg" / "a.py").resolve()
    for bad in ("../secret.py", str(tmp_path / "secret.py"), "pkg", "pkg/missing.py"):
        with pytest.raises(desktop.DesktopError):
            desktop.resolve_source_file(root, bad)
    with pytest.raises(desktop.DesktopError, match="no source folder"):
        desktop.resolve_source_file(tmp_path / "gone", "a.py")


@pytest.mark.parametrize(
    ("host", "local"),
    [
        ("127.0.0.1", True),
        ("localhost", True),
        ("::1", True),
        ("[::1]", True),
        ("192.168.1.20", False),
        ("evil.example", False),
        ("testclient", False),
        (None, False),
    ],
)
def test_is_loopback(host, local):
    assert desktop.is_loopback(host) is local


# ---------- reveal ----------

@pytest.mark.parametrize(
    ("platform", "expected"),
    [
        ("win32", ["explorer", "/select,", "{path}"]),
        ("darwin", ["open", "-R", "{path}"]),
        ("linux", ["xdg-open", "{parent}"]),
    ],
)
def test_reveal_uses_the_file_manager_of_the_platform(
    monkeypatch, spawned, tmp_path, platform, expected
):
    monkeypatch.setattr(sys, "platform", platform)
    path = tmp_path / "a.cs"
    desktop.reveal(path)
    assert spawned == [[p.format(path=path, parent=path.parent) for p in expected]]


# ---------- open in editor ----------

@pytest.fixture
def no_vscode(monkeypatch) -> None:
    """A machine without VS Code, so the desktop default is what opens a file."""
    monkeypatch.setattr(desktop, "find_vscode", lambda: None)


def test_vscode_opens_every_file_type_when_it_is_installed(monkeypatch, spawned, started, tmp_path):
    monkeypatch.delenv(desktop.EDITOR_ENV, raising=False)
    monkeypatch.setattr(desktop, "find_vscode", lambda: "/apps/code")
    cs, py = tmp_path / "Invoice.cs", tmp_path / "billing.py"

    desktop.open_in_editor(cs, 12)
    desktop.open_in_editor(py)  # a script: opened, never run
    assert spawned == [["/apps/code", "-g", f"{cs}:12"], ["/apps/code", "-g", f"{py}:1"]]
    assert started == [], "the desktop default must not be used when VS Code is there"


def test_cdec_editor_wins_over_vscode(monkeypatch, spawned, tmp_path):
    monkeypatch.setenv(desktop.EDITOR_ENV, "myeditor")
    monkeypatch.setattr(desktop, "find_vscode", lambda: "/apps/code")
    desktop.open_in_editor(tmp_path / "a.cs")
    assert spawned == [["myeditor", str(tmp_path / "a.cs")]]


def test_find_vscode_on_the_path(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "linux")
    code = tmp_path / "code"
    code.write_text("", encoding="utf-8")
    monkeypatch.setattr(desktop.shutil, "which", lambda name: str(code) if name == "code" else None)
    assert desktop.find_vscode() == str(code)

    monkeypatch.setattr(desktop.shutil, "which", lambda name: None)
    assert desktop.find_vscode() is None


def test_find_vscode_on_windows_starts_the_program_not_the_batch_file(monkeypatch, tmp_path):
    """`code` is `<install>/bin/code.cmd` on Windows. A batch file goes through
    cmd.exe; the program next to it does not."""
    monkeypatch.setattr(sys, "platform", "win32")
    install = tmp_path / "Microsoft VS Code"
    (install / "bin").mkdir(parents=True)
    (install / "bin" / "code.cmd").write_text("", encoding="utf-8")
    (install / "Code.exe").write_text("", encoding="utf-8")
    monkeypatch.setattr(desktop.shutil, "which", lambda name: str(install / "bin" / "code.cmd"))
    assert desktop.find_vscode() == str(install / "Code.exe")


def test_find_vscode_in_the_install_folder_when_it_is_not_on_the_path(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(desktop.shutil, "which", lambda name: None)
    for var in ("ProgramFiles", "ProgramFiles(x86)"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert desktop.find_vscode() is None

    install = tmp_path / "Programs" / "Microsoft VS Code"
    (install / "bin").mkdir(parents=True)
    (install / "bin" / "code.cmd").write_text("", encoding="utf-8")
    (install / "Code.exe").write_text("", encoding="utf-8")
    assert desktop.find_vscode() == str(install / "Code.exe")


def test_open_uses_the_default_application_on_windows(monkeypatch, started, no_vscode, tmp_path):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.delenv(desktop.EDITOR_ENV, raising=False)
    monkeypatch.setenv("PATHEXT", ".COM;.EXE;.BAT;.CMD;.PY")
    desktop.open_in_editor(tmp_path / "Invoice.cs")
    assert started == [(str(tmp_path / "Invoice.cs"), "open")]


def test_open_never_runs_a_script_on_windows(monkeypatch, started, no_vscode, tmp_path):
    """`.py` is in PATHEXT once Python is installed: "open" would run the file."""
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.delenv(desktop.EDITOR_ENV, raising=False)
    monkeypatch.setenv("PATHEXT", ".COM;.EXE;.BAT;.CMD;.PY")
    desktop.open_in_editor(tmp_path / "billing.py")
    assert started == [(str(tmp_path / "billing.py"), "edit")]


def test_open_explains_when_windows_has_no_editor_for_a_script(monkeypatch, no_vscode, tmp_path):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.delenv(desktop.EDITOR_ENV, raising=False)
    monkeypatch.setenv("PATHEXT", ".COM;.EXE;.PY")

    def no_edit_verb(path, verb="open"):
        assert verb == "edit", "the file must not be opened with the run verb"
        raise OSError("no application is associated")

    monkeypatch.setattr(os, "startfile", no_edit_verb, raising=False)
    with pytest.raises(desktop.DesktopError, match=desktop.EDITOR_ENV):
        desktop.open_in_editor(tmp_path / "billing.py")


def test_cdec_editor_wins_and_fills_the_placeholders(monkeypatch, spawned, started, tmp_path):
    monkeypatch.setenv(desktop.EDITOR_ENV, "myeditor -g {file}:{line}")
    path = tmp_path / "billing.py"
    desktop.open_in_editor(path, 42)
    assert spawned == [["myeditor", "-g", f"{path}:42"]]
    assert started == []

    # Without {file} the path goes at the end.
    spawned.clear()
    monkeypatch.setenv(desktop.EDITOR_ENV, "myeditor --wait")
    desktop.open_in_editor(path)
    assert spawned == [["myeditor", "--wait", str(path)]]


@pytest.mark.parametrize(
    ("platform", "expected"), [("darwin", ["open", "-t"]), ("linux", ["xdg-open"])]
)
def test_open_on_other_platforms(monkeypatch, spawned, no_vscode, tmp_path, platform, expected):
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.delenv(desktop.EDITOR_ENV, raising=False)
    path = tmp_path / "a.py"
    desktop.open_in_editor(path)
    assert spawned == [[*expected, str(path)]]


# ---------- the API ----------

@pytest.fixture
def parsed(monkeypatch, tmp_path) -> tuple[TestClient, str, dict]:
    """A local client, the id of a parsed model, and one of its class nodes."""
    monkeypatch.setattr(web_app, "CACHE_ROOT", tmp_path / ".cdec_cache")
    client = TestClient(web_app.app, client=("127.0.0.1", 50000))
    pid = client.post(
        "/api/projects", json={"path": str(FIXTURES / "python_demo"), "lang": "python"}
    ).json()["id"]
    xmi_id = client.post(f"/api/projects/{pid}/parse").json()["id"]
    nodes = client.get(f"/api/xmi/{xmi_id}/model").json()["nodes"]
    node = next(n for n in nodes if n["location"])
    return client, xmi_id, node


def test_api_reveals_and_opens_the_file_of_a_class(monkeypatch, parsed):
    client, xmi_id, node = parsed
    seen: list[tuple[str, Path, int | None]] = []
    monkeypatch.setattr(desktop, "reveal", lambda p: seen.append(("reveal", p, None)))
    monkeypatch.setattr(desktop, "open_in_editor", lambda p, line=None: seen.append(("open", p, line)))

    assert client.post(f"/api/xmi/{xmi_id}/nodes/{node['id']}/reveal").status_code == 204
    assert client.post(f"/api/xmi/{xmi_id}/nodes/{node['id']}/open").status_code == 204

    expected = (FIXTURES / "python_demo" / node["location"]["file"]).resolve()
    assert seen == [("reveal", expected, None), ("open", expected, node["location"]["startLine"])]


def test_api_refuses_unknown_nodes_and_actions(monkeypatch, parsed):
    client, xmi_id, node = parsed
    monkeypatch.setattr(desktop, "reveal", lambda p: pytest.fail("must not reach the desktop"))
    assert client.post(f"/api/xmi/{xmi_id}/nodes/class-0000000000000000/reveal").status_code == 404
    assert client.post(f"/api/xmi/{xmi_id}/nodes/{node['id']}/delete").status_code == 404
    assert client.post(f"/api/xmi/nosuchxmi/nodes/{node['id']}/reveal").status_code == 404


def test_api_desktop_actions_are_for_this_machine_only(monkeypatch, parsed):
    """A page on another site, or a client on the network, must not be able to
    open windows on the desktop of the user."""
    client, xmi_id, node = parsed
    monkeypatch.setattr(desktop, "reveal", lambda p: pytest.fail("must not reach the desktop"))
    url = f"/api/xmi/{xmi_id}/nodes/{node['id']}/reveal"

    # A cross-site request from the browser of the user: local client, foreign origin.
    assert client.post(url, headers={"Origin": "https://evil.example"}).status_code == 403
    # A client that is not this machine.
    remote = TestClient(web_app.app, client=("192.168.1.20", 50000))
    assert remote.post(url).status_code == 403

    # The viewer itself, and the Vite dev server, are local origins.
    monkeypatch.setattr(desktop, "reveal", lambda p: None)
    assert client.post(url, headers={"Origin": "http://127.0.0.1:8765"}).status_code == 204
    assert client.post(url, headers={"Origin": "http://localhost:5173"}).status_code == 204
