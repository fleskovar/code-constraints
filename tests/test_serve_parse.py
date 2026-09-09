"""Tests for `cdec serve parse` — language auto-detection and the CLI wiring."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from code_constraints.cli.__main__ import app
from code_constraints.cli.detect import detect_language

FIXTURES = Path(__file__).parent / "fixtures"
runner = CliRunner()


# ---------- detect_language ----------

def test_detect_python_demo():
    assert detect_language(FIXTURES / "python_demo") == "python"


def test_detect_csharp_demo():
    assert detect_language(FIXTURES / "csharp_demo") == "csharp"


def test_detect_typescript_demo():
    assert detect_language(FIXTURES / "typescript_demo") == "typescript"


def test_detect_svelte_demo():
    assert detect_language(FIXTURES / "svelte_demo") == "svelte"


def test_svelte_file_wins_over_typescript(tmp_path: Path):
    # A mostly-TS tree with a single .svelte file is detected as svelte.
    (tmp_path / "a.ts").write_text("export const a = 1;\n", encoding="utf-8")
    (tmp_path / "b.ts").write_text("export const b = 2;\n", encoding="utf-8")
    (tmp_path / "App.svelte").write_text("<script></script>\n", encoding="utf-8")
    assert detect_language(tmp_path) == "svelte"


def test_majority_extension_wins(tmp_path: Path):
    (tmp_path / "one.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "two.py").write_text("y = 2\n", encoding="utf-8")
    (tmp_path / "lone.cs").write_text("class C {}\n", encoding="utf-8")
    assert detect_language(tmp_path) == "python"


def test_ignores_vendor_dirs(tmp_path: Path):
    # .ts files buried in node_modules must not sway detection.
    (tmp_path / "main.py").write_text("x = 1\n", encoding="utf-8")
    vendored = tmp_path / "node_modules" / "pkg"
    vendored.mkdir(parents=True)
    for i in range(5):
        (vendored / f"f{i}.ts").write_text("export {}\n", encoding="utf-8")
    assert detect_language(tmp_path) == "python"


def test_empty_dir_returns_none(tmp_path: Path):
    assert detect_language(tmp_path) is None


# ---------- CLI wiring ----------

def test_serve_help_lists_parse():
    result = runner.invoke(app, ["serve", "--help"])
    assert result.exit_code == 0
    assert "parse" in result.output


def test_bare_serve_runs_server(monkeypatch):
    calls: dict = {}

    def fake_run(host, port, open_url=None):
        calls["host"] = host
        calls["port"] = port
        calls["open_url"] = open_url

    monkeypatch.setattr("code_constraints.cli.__main__._run_server", fake_run)
    result = runner.invoke(app, ["serve", "--port", "9001"])
    assert result.exit_code == 0
    assert calls == {"host": "127.0.0.1", "port": 9001, "open_url": None}


def test_serve_parse_autodetects_and_opens_url(monkeypatch):
    calls: dict = {}

    def fake_run(host, port, open_url=None):
        calls["host"] = host
        calls["port"] = port
        calls["open_url"] = open_url

    monkeypatch.setattr("code_constraints.cli.__main__._run_server", fake_run)
    result = runner.invoke(app, ["serve", "parse", str(FIXTURES / "python_demo")])
    assert result.exit_code == 0
    assert calls["open_url"] is not None
    assert "lang=python" in calls["open_url"]
    assert "path=" in calls["open_url"]


def test_serve_parse_respects_explicit_lang(monkeypatch):
    calls: dict = {}
    monkeypatch.setattr(
        "code_constraints.cli.__main__._run_server",
        lambda host, port, open_url=None: calls.update(open_url=open_url),
    )
    result = runner.invoke(
        app, ["serve", "parse", str(FIXTURES / "python_demo"), "--lang", "csharp"]
    )
    assert result.exit_code == 0
    assert "lang=csharp" in calls["open_url"]


def test_serve_parse_errors_when_undetectable(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "code_constraints.cli.__main__._run_server",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not run")),
    )
    result = runner.invoke(app, ["serve", "parse", str(tmp_path)])
    assert result.exit_code != 0
    assert "auto-detect" in result.output
