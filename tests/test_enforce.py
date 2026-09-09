"""Tests for the `cdec enforce` conformance engine (Engine B).

Each architectural-rule body check (`sealed`, `immutable`, `factory`,
`no-instantiation`) must catch a seeded violation and stay silent on clean
code, for both Python and C#.

The shared `python_rules` / `csharp_rules` fixtures seed sealed/immutable/
factory violations. Their `no-instantiation` methods are intentionally clean
(they don't construct project types), so the no-instantiation cases use inline
snippets under `tmp_path`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from code_constraints.enforce import enforce

PY_RULES = Path(__file__).parent / "fixtures" / "python_rules"
CS_RULES = Path(__file__).parent / "fixtures" / "csharp_rules"


def _rules(findings, rule):
    return [f for f in findings if f.rule == rule]


# ---------- fixture-based: sealed / immutable / factory ----------

def test_python_fixture_catches_seeded_violations():
    findings = enforce(PY_RULES, "python")
    assert _rules(findings, "sealed"), "expected a sealed violation"
    assert _rules(findings, "immutable"), "expected an immutable violation"
    assert _rules(findings, "factory"), "expected a factory violation"
    # The tagged no-instantiation methods are clean.
    assert not _rules(findings, "no-instantiation")


def test_csharp_fixture_catches_seeded_violations():
    findings = enforce(CS_RULES, "csharp")
    assert _rules(findings, "sealed")
    assert _rules(findings, "immutable")
    assert _rules(findings, "factory")
    assert not _rules(findings, "no-instantiation")


def test_python_sealed_points_at_subclass():
    findings = _rules(enforce(PY_RULES, "python"), "sealed")
    assert any("SpecialRepository" in f.qualified_name for f in findings)


def test_csharp_factory_points_at_offender():
    findings = _rules(enforce(CS_RULES, "csharp"), "factory")
    assert any("Sneaky" in f.qualified_name for f in findings)


# ---------- inline: no-instantiation (violation + clean) ----------

PY_NOINST_BAD = """\
from cdec_rules import no_instantiation


class Widget:
    pass


class Builder:
    @no_instantiation
    def run(self):
        return Widget()
"""

PY_NOINST_CLEAN = """\
from cdec_rules import no_instantiation


class Widget:
    pass


class Builder:
    @no_instantiation(allow=["Widget"])
    def run(self):
        return Widget()
"""

CS_NOINST_BAD = """\
using CodeConstraints.Rules;
namespace App
{
    public class Widget { }

    public class Builder
    {
        [NoInstantiation]
        public Widget Run() { return new Widget(); }
    }
}
"""

CS_NOINST_CLEAN = """\
using CodeConstraints.Rules;
namespace App
{
    public class Widget { }

    public class Builder
    {
        [NoInstantiation(Allow = new[] { "Widget" })]
        public Widget Run() { return new Widget(); }
    }
}
"""


def _write(tmp_path: Path, name: str, body: str) -> Path:
    (tmp_path / name).write_text(body, encoding="utf-8")
    return tmp_path


def test_python_no_instantiation_fires(tmp_path):
    root = _write(tmp_path, "m.py", PY_NOINST_BAD)
    assert _rules(enforce(root, "python"), "no-instantiation")


def test_python_no_instantiation_allow_silences(tmp_path):
    root = _write(tmp_path, "m.py", PY_NOINST_CLEAN)
    assert not _rules(enforce(root, "python"), "no-instantiation")


def test_csharp_no_instantiation_fires(tmp_path):
    root = _write(tmp_path, "M.cs", CS_NOINST_BAD)
    assert _rules(enforce(root, "csharp"), "no-instantiation")


def test_csharp_no_instantiation_allow_silences(tmp_path):
    root = _write(tmp_path, "M.cs", CS_NOINST_CLEAN)
    assert not _rules(enforce(root, "csharp"), "no-instantiation")


# ---------- clean codebases stay silent ----------

PY_CLEAN = """\
class Plain:
    def go(self):
        return 1
"""

CS_CLEAN = """\
namespace App
{
    public class Plain
    {
        public int Go() { return 1; }
    }
}
"""


def test_python_untagged_code_has_no_findings(tmp_path):
    root = _write(tmp_path, "m.py", PY_CLEAN)
    assert enforce(root, "python") == []


def test_csharp_untagged_code_has_no_findings(tmp_path):
    root = _write(tmp_path, "M.cs", CS_CLEAN)
    assert enforce(root, "csharp") == []
