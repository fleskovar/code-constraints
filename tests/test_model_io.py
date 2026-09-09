"""Tests for the JSON model format (`code_constraints.core.model_io`) and `cdec convert` /
`cdec reference set` — the authoring-friendly alternatives to hand-written XMI."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from code_constraints.cli.__main__ import app
from code_constraints.core.model import (
    Attribute,
    Class,
    Operation,
    Package,
    Project,
    RuleAnnotation,
)
from code_constraints.core.model_io import UnsupportedModelFormat, load_model, save_model
from code_constraints.python import parse_project

FIXTURE = Path(__file__).parent / "fixtures" / "python_demo"


def _sample_project() -> Project:
    cls = Class(
        name="Invoice",
        qualified_name="billing.Invoice",
        kind="class",
        attributes=[Attribute(name="total", type="float")],
        operations=[
            Operation(
                name="pay",
                return_type="bool",
                rules=[RuleAnnotation(name="no-side-effects")],
            )
        ],
        bases=["billing.Document"],
        rules=[RuleAnnotation(name="immutable"), RuleAnnotation(name="layer", args=['"domain"'])],
    )
    pkg = Package(name="billing", qualified_name="billing", classes=[cls])
    return Project(source_language="python", packages=[pkg])


def test_json_round_trip_preserves_structure_and_rules(tmp_path: Path) -> None:
    proj = _sample_project()
    out = tmp_path / "model.json"
    save_model(proj, out)
    loaded = load_model(out)

    assert loaded.source_language == "python"
    assert loaded.packages == proj.packages  # dataclass equality, incl. rules


def test_json_round_trip_of_parsed_fixture(tmp_path: Path) -> None:
    proj = parse_project(FIXTURE)
    json_path = tmp_path / "demo.json"
    save_model(proj, json_path)
    loaded = load_model(json_path)

    orig = {c.qualified_name for c in proj.iter_classes()}
    back = {c.qualified_name for c in loaded.iter_classes()}
    assert orig == back
    assert loaded.source_language == proj.source_language


def test_xmi_and_json_agree(tmp_path: Path) -> None:
    proj = _sample_project()
    save_model(proj, tmp_path / "m.xmi")
    save_model(proj, tmp_path / "m.json")
    from_xmi = load_model(tmp_path / "m.xmi")
    from_json = load_model(tmp_path / "m.json")
    assert {c.qualified_name for c in from_xmi.iter_classes()} == {
        c.qualified_name for c in from_json.iter_classes()
    }


def test_unknown_extension_rejected(tmp_path: Path) -> None:
    proj = _sample_project()
    with pytest.raises(UnsupportedModelFormat):
        save_model(proj, tmp_path / "m.yaml")
    (tmp_path / "m.txt").write_text("nope", encoding="utf-8")
    with pytest.raises(UnsupportedModelFormat):
        load_model(tmp_path / "m.txt")


def test_convert_cli_both_directions(tmp_path: Path) -> None:
    runner = CliRunner()
    r = runner.invoke(
        app,
        ["parse", str(FIXTURE), "--lang", "python", "--out", str(tmp_path / "a.json")],
    )
    assert r.exit_code == 0, r.output
    r = runner.invoke(
        app, ["convert", str(tmp_path / "a.json"), str(tmp_path / "a.xmi")]
    )
    assert r.exit_code == 0, r.output
    r = runner.invoke(
        app, ["convert", str(tmp_path / "a.xmi"), str(tmp_path / "b.json")]
    )
    assert r.exit_code == 0, r.output

    a = load_model(tmp_path / "a.json")
    b = load_model(tmp_path / "b.json")
    assert {c.qualified_name for c in a.iter_classes()} == {
        c.qualified_name for c in b.iter_classes()
    }


def test_reference_set_locks_json_model_as_xmi(tmp_path: Path) -> None:
    proj = _sample_project()
    model_path = tmp_path / "target.json"
    save_model(proj, model_path)

    config_dir = tmp_path / ".cdec"
    runner = CliRunner()
    r = runner.invoke(
        app,
        ["reference", "set", str(model_path), "--config", str(config_dir)],
    )
    assert r.exit_code == 0, r.output
    ref_path = config_dir / "reference.xmi"
    assert ref_path.is_file()
    locked = load_model(ref_path)
    assert {c.qualified_name for c in locked.iter_classes()} == {"billing.Invoice"}
