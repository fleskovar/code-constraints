"""Odin parser tests, run against `tests/fixtures/odin_demo`.

Locks the two mapping decisions Odin forces (procedures belong to their first
parameter; `using` embedding is inheritance) plus the tree-sitter details that
would silently produce a wrong model if they regressed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from code_constraints.core.model import Visibility
from code_constraints.odin import parse_project

FIXTURE = Path(__file__).parent / "fixtures" / "odin_demo"


@pytest.fixture(scope="module")
def project():
    return parse_project(FIXTURE)


def _cls(project, qn):
    return next(c for c in project.iter_classes() if c.qualified_name == qn)


def test_structs_and_enums_become_classes(project):
    kinds = {c.qualified_name: c.kind for c in project.iter_classes()}
    assert kinds["billing.Invoice"] == "struct"
    assert kinds["billing.Money"] == "struct"
    assert kinds["billing.Status"] == "enum"


def test_package_comes_from_the_directory(project):
    assert {c.qualified_name.split(".")[0] for c in project.iter_classes()} == {"billing"}


def test_struct_fields_carry_types(project):
    money = _cls(project, "billing.Money")
    assert [(a.name, a.type) for a in money.attributes] == [
        ("amount", "f64"),
        ("currency", "string"),
    ]


def test_enum_members_become_static_attributes(project):
    status = _cls(project, "billing.Status")
    assert [a.name for a in status.attributes] == ["Draft", "Sent", "Paid"]
    assert all(a.is_static for a in status.attributes)


def test_using_embedding_is_inheritance_not_a_field(project):
    # `using base: Invoice` is Odin's subtype mechanism, so it must draw as an
    # inheritance edge rather than as an attribute named `base`.
    detailed = _cls(project, "billing.Detailed")
    assert detailed.bases == ["Invoice"]
    assert [a.name for a in detailed.attributes] == ["note"]


def test_procedures_attach_to_their_receiver_struct(project):
    invoice = _cls(project, "billing.Invoice")
    assert {op.name for op in invoice.operations} == {"formatted", "summarise"}


def test_receiver_is_dropped_from_the_signature(project):
    # The receiver is `self` in UML terms, so `proc(inv: ^Invoice, verbose: bool)`
    # shows only `verbose`.
    invoice = _cls(project, "billing.Invoice")
    summarise = next(op for op in invoice.operations if op.name == "summarise")
    assert [p.name for p in summarise.parameters] == ["verbose"]
    assert not summarise.is_static


def test_multiple_return_values_are_kept_as_the_return_type(project):
    invoice = _cls(project, "billing.Invoice")
    summarise = next(op for op in invoice.operations if op.name == "summarise")
    assert summarise.return_type == "(out: string, ok: bool)"


def test_receiverless_procedures_land_on_a_static_module_class(project):
    # Without this a tag on a package-scope procedure would be silently dropped.
    module = _cls(project, "billing.invoice")
    assert module.kind == "static"
    assert [op.name for op in module.operations] == ["helper"]
    assert module.operations[0].is_static


def test_private_attribute_marks_visibility(project):
    module = _cls(project, "billing.invoice")
    assert module.operations[0].visibility is Visibility.PRIVATE


def test_class_rules_come_from_annotation_comments(project):
    invoice = _cls(project, "billing.Invoice")
    assert [r.name for r in invoice.rules] == ["sealed", "layer"]
    assert invoice.rules[1].args == ['"domain"']


def test_operation_rules_come_from_annotation_comments(project):
    invoice = _cls(project, "billing.Invoice")
    formatted = next(op for op in invoice.operations if op.name == "formatted")
    assert [r.name for r in formatted.rules] == ["locked"]
    assert formatted.rules[0].kwargs == {"reason": '"agreed rounding"'}


def test_dependencies_resolve_pointer_and_collection_wrappers(project):
    invoice = _cls(project, "billing.Invoice")
    assert "Money" in invoice.dependencies
    assert "Status" in invoice.dependencies


def test_shim_file_is_not_parsed_as_a_class(tmp_path):
    # A copied `cdec_rules.odin` declares the vocabulary as no-op procedures;
    # parsing it would put a spurious module class in the user's own diagram.
    (tmp_path / "cdec_rules.odin").write_text(
        "package cdec_rules\nsealed :: proc() {}\n", encoding="utf-8"
    )
    (tmp_path / "real.odin").write_text(
        "package app\nThing :: struct { x: int }\n", encoding="utf-8"
    )
    parsed = parse_project(tmp_path)
    assert [c.name for c in parsed.iter_classes()] == ["Thing"]
