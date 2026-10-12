"""Tests for the hcm bundle that ships in the package, and for `cdec hcm`.

The integration tests drive the real `hcm` command against a temporary
`HCM_HOME`, so they never touch the developer's own registry, and they install
at project scope only — `HCM_HOME` does not move the harness home folders. They
are skipped where hcm is not installed.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from code_constraints.cli import hcm as bridge
from code_constraints.cli.__main__ import app

REPO_ROOT = Path(__file__).resolve().parents[1]
HCM = shutil.which("hcm")
needs_hcm = pytest.mark.skipif(HCM is None, reason="hcm is not installed")

runner = CliRunner()


def _package_version() -> str:
    with (REPO_ROOT / "pyproject.toml").open("rb") as fh:
        return tomllib.load(fh)["project"]["version"]


def _registry_entry() -> dict:
    out = subprocess.run(
        [HCM, "registry", "list", "--json"], capture_output=True, text=True, check=True
    )
    return next(e for e in json.loads(out.stdout) if e["name"] == bridge.BUNDLE_NAME)


def test_bundle_version_matches_the_package():
    """The bundle ships inside the package, so one version describes both."""
    manifest = yaml.safe_load((bridge.BUNDLE_DIR / "hcm.yaml").read_text(encoding="utf-8"))

    assert manifest["name"] == bridge.BUNDLE_NAME
    assert manifest["version"] == _package_version()


def test_init_without_hcm_names_the_install_command(monkeypatch):
    """A missing hcm is a dead end unless the error says how to get it."""
    monkeypatch.setattr(shutil, "which", lambda _name: None)

    result = runner.invoke(app, ["hcm", "init"])

    assert result.exit_code == 1
    assert "npm install -g harness-config-manager" in result.output


@needs_hcm
def test_bundle_passes_hcm_validation():
    # An absolute path: hcm reads a bare relative one as a GitHub reference.
    bundle = str(bridge.BUNDLE_DIR)

    assert subprocess.run([HCM, "validate", bundle], check=False).returncode == 0
    assert subprocess.run([HCM, "refs", "check", "--path", bundle], check=False).returncode == 0


@needs_hcm
def test_init_and_update_carry_the_bundle_into_a_project(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setenv("HCM_HOME", str(tmp_path / "hcm-home"))
    monkeypatch.chdir(project)

    assert runner.invoke(app, ["hcm", "init"]).exit_code == 0
    entry = _registry_entry()
    assert entry["version"] == _package_version()
    assert not entry.get("dev")

    install = [HCM, "install", bridge.BUNDLE_NAME, "-t", "claude-code", "--no-prompt"]
    assert subprocess.run(install, check=False).returncode == 0
    assert (project / ".claude/skills/cdec-architecture-first/SKILL.md").is_file()
    assert (project / ".claude/agents/cdec-architect.md").is_file()

    # Registering again is the upgrade path, so it must not mint a new entry.
    assert runner.invoke(app, ["hcm", "init"]).exit_code == 0
    assert _registry_entry()["id"] == entry["id"]

    assert runner.invoke(app, ["hcm", "update", "--no-prompt"]).exit_code == 0
    assert subprocess.run([HCM, "status"], check=False).returncode == 0

    # `update` must leave a development registration alone: re-registering it
    # without --dev would swap the working copy for a stored snapshot.
    assert runner.invoke(app, ["hcm", "init", "--dev"]).exit_code == 0
    assert runner.invoke(app, ["hcm", "update", "--no-prompt"]).exit_code == 0
    dev_entry = _registry_entry()
    assert dev_entry["dev"] is True
    assert dev_entry["id"] == entry["id"]
