"""Lua parser tests, run against `tests/fixtures/lua_demo`.

Lua has no classes, so most of these lock the *promotion* rule — which tables
become classes and which stay plain locals — plus the metatable idioms that map
to inheritance and instance state.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from code_constraints.core.model import Visibility
from code_constraints.lua import parse_project

FIXTURE = Path(__file__).parent / "fixtures" / "lua_demo"


@pytest.fixture(scope="module")
def project():
    return parse_project(FIXTURE)


def _cls(project, qn):
    return next(c for c in project.iter_classes() if c.qualified_name == qn)


def test_table_with_methods_becomes_a_class(project):
    assert _cls(project, "billing.Invoice").kind == "class"


def test_plain_data_table_is_not_promoted(project):
    # `local scratch = {}` has no methods, no __index, no base and no tag, so it
    # must not appear — otherwise every scratch local pollutes the diagram.
    assert not any(c.name == "scratch" for c in project.iter_classes())


def test_required_module_local_is_not_promoted(project):
    # `local Money = require(...)` binds a name but declares nothing.
    assert not any(c.name == "Money" for c in project.iter_classes())


def test_metatable_index_is_inheritance(project):
    detailed = _cls(project, "billing.Detailed")
    assert detailed.bases == ["Invoice"]


def test_colon_methods_are_instance_methods(project):
    invoice = _cls(project, "billing.Invoice")
    formatted = next(op for op in invoice.operations if op.name == "formatted")
    assert not formatted.is_static


def test_dot_functions_are_static(project):
    invoice = _cls(project, "billing.Invoice")
    new = next(op for op in invoice.operations if op.name == "new")
    assert new.is_static


def test_instance_attributes_come_from_self_assignments(project):
    invoice = _cls(project, "billing.Invoice")
    names = [a.name for a in invoice.attributes]
    assert "id" in names and "total" in names


def test_instance_attributes_keep_constructor_order(project):
    # Attribute order is user-visible in the class box and is what the diff
    # compares, so the walk must follow source order rather than a LIFO stack.
    invoice = _cls(project, "billing.Invoice")
    instance = [a.name for a in invoice.attributes if not a.is_static]
    assert instance == ["id", "total", "_audit"]


def test_table_field_is_a_static_attribute(project):
    invoice = _cls(project, "billing.Invoice")
    currency = next(a for a in invoice.attributes if a.name == "CURRENCY")
    assert currency.is_static
    assert currency.default == '"USD"'


def test_metafields_are_not_attributes(project):
    invoice = _cls(project, "billing.Invoice")
    assert "__index" not in [a.name for a in invoice.attributes]


def test_leading_underscore_is_private_by_convention(project):
    invoice = _cls(project, "billing.Invoice")
    audit = next(a for a in invoice.attributes if a.name == "_audit")
    assert audit.visibility is Visibility.PRIVATE


def test_varargs_are_kept_as_a_parameter(project):
    invoice = _cls(project, "billing.Invoice")
    summarise = next(op for op in invoice.operations if op.name == "summarise")
    assert [p.name for p in summarise.parameters] == ["verbose", "..."]


def test_class_and_operation_rules_come_from_annotation_comments(project):
    invoice = _cls(project, "billing.Invoice")
    assert [r.name for r in invoice.rules] == ["sealed", "layer"]
    formatted = next(op for op in invoice.operations if op.name == "formatted")
    assert [r.name for r in formatted.rules] == ["locked"]


def test_free_functions_land_on_a_static_module_class(project):
    module = _cls(project, "billing.invoice")
    assert module.kind == "static"
    assert [op.name for op in module.operations] == ["helper"]


def test_a_tag_alone_promotes_a_table(tmp_path):
    # Tagging a table must be enough to pull it into the model even before it
    # has methods — otherwise a fresh design can't be described.
    (tmp_path / "m.lua").write_text(
        '---@cdec layer("domain")\nlocal Empty = {}\nreturn Empty\n', encoding="utf-8"
    )
    parsed = parse_project(tmp_path)
    assert [c.name for c in parsed.iter_classes()] == ["Empty"]


def test_shim_file_is_not_parsed_as_a_class(tmp_path):
    (tmp_path / "cdec_rules.lua").write_text(
        "local cdec = {}\nfunction cdec.sealed(x) return x end\nreturn cdec\n",
        encoding="utf-8",
    )
    (tmp_path / "real.lua").write_text(
        "local Thing = {}\nThing.__index = Thing\nfunction Thing:go() end\n",
        encoding="utf-8",
    )
    parsed = parse_project(tmp_path)
    assert [c.name for c in parsed.iter_classes()] == ["Thing"]
