"""Julia parser tests, run against `tests/fixtures/julia_demo`.

The interesting cases here are the macro shapes: tree-sitter flattens stacked
macros into siblings while real Julia nests them, and `@locked reason="…"` puts
its keywords beside the definition in the same argument list. Both are locked
below, along with the first-argument-is-the-receiver mapping.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from code_constraints.julia import parse_project
from code_constraints.julia.rules_extract import foreign_macros, using_has_shim

FIXTURE = Path(__file__).parent / "fixtures" / "julia_demo"


@pytest.fixture(scope="module")
def project():
    return parse_project(FIXTURE)


def _cls(project, qn):
    return next(c for c in project.iter_classes() if c.qualified_name == qn)


def test_modules_nest_inside_the_directory_package(project):
    assert _cls(project, "billing.Billing.Invoice").name == "Invoice"


def test_struct_and_abstract_type_kinds(project):
    assert _cls(project, "billing.Billing.Invoice").kind == "struct"
    assert _cls(project, "billing.Billing.AbstractInvoice").kind == "abstract"


def test_subtype_operator_is_inheritance(project):
    assert _cls(project, "billing.Billing.Invoice").bases == ["AbstractInvoice"]


def test_fields_carry_types(project):
    money = _cls(project, "billing.Billing.Money")
    assert [(a.name, a.type) for a in money.attributes] == [
        ("amount", "Float64"),
        ("currency", "String"),
    ]


def test_immutable_struct_fields_are_readonly(project):
    # A non-`mutable struct` genuinely cannot be reassigned, so the model says so.
    assert all(a.is_readonly for a in _cls(project, "billing.Billing.Money").attributes)


def test_mutable_struct_fields_are_not_readonly(project):
    assert not any(a.is_readonly for a in _cls(project, "billing.Billing.Draft").attributes)


def test_parametrised_field_type_is_kept_verbatim(project):
    draft = _cls(project, "billing.Billing.Draft")
    assert draft.attributes[0].type == "Vector{String}"


def test_functions_attach_to_their_first_argument_type(project):
    invoice = _cls(project, "billing.Billing.Invoice")
    assert {"formatted", "summarise", "total_of"} <= {op.name for op in invoice.operations}


def test_short_form_function_is_an_operation(project):
    # `total_of(inv::Invoice) = inv.total` is an `assignment`, not a
    # `function_definition`, and must still be recognised.
    invoice = _cls(project, "billing.Billing.Invoice")
    assert "total_of" in {op.name for op in invoice.operations}


def test_inner_constructor_is_an_operation_of_its_struct(project):
    invoice = _cls(project, "billing.Billing.Invoice")
    assert "Invoice" in {op.name for op in invoice.operations}


def test_receiver_is_dropped_and_keywords_are_kept(project):
    invoice = _cls(project, "billing.Billing.Invoice")
    summarise = next(op for op in invoice.operations if op.name == "summarise")
    assert [p.name for p in summarise.parameters] == ["verbose", "short"]


def test_return_type_annotation_is_captured(project):
    invoice = _cls(project, "billing.Billing.Invoice")
    formatted = next(op for op in invoice.operations if op.name == "formatted")
    assert formatted.return_type == "String"


def test_stacked_macros_all_register_as_rules(project):
    # `@sealed @layer "domain" struct …`: tree-sitter emits @layer and the struct
    # as siblings inside @sealed's argument list, so both tags must be collected
    # and the struct must still be found.
    invoice = _cls(project, "billing.Billing.Invoice")
    assert [r.name for r in invoice.rules] == ["sealed", "layer"]
    assert invoice.rules[1].args == ['"domain"']


def test_macro_keyword_arguments_become_rule_kwargs(project):
    invoice = _cls(project, "billing.Billing.Invoice")
    formatted = next(op for op in invoice.operations if op.name == "formatted")
    assert formatted.rules[0].kwargs == {"reason": '"agreed rounding"'}


def test_receiverless_functions_land_on_a_static_module_class(project):
    module = _cls(project, "billing.Billing.invoice")
    assert module.kind == "static"
    assert [op.name for op in module.operations] == ["helper"]


def test_macros_are_ignored_without_the_shim_import(tmp_path):
    # A user's own `@sealed` must never be misread as a rule.
    (tmp_path / "m.jl").write_text(
        "macro sealed(x) esc(x) end\n@sealed struct T\n    a::Int\nend\n",
        encoding="utf-8",
    )
    parsed = parse_project(tmp_path)
    thing = next(c for c in parsed.iter_classes() if c.name == "T")
    assert thing.rules == []


def test_unknown_macro_still_yields_the_definition(tmp_path):
    # Peeling an unrelated wrapper matters: otherwise `Base.@kwdef struct …`
    # would hide the struct from the model entirely.
    (tmp_path / "m.jl").write_text(
        "using CdecRules\nBase.@kwdef struct T\n    a::Int = 1\nend\n", encoding="utf-8"
    )
    parsed = parse_project(tmp_path)
    assert [c.name for c in parsed.iter_classes()] == ["T"]


def test_foreign_macros_lists_only_non_rule_macros():
    import tree_sitter_julia
    from tree_sitter import Language, Parser

    parser = Parser(Language(tree_sitter_julia.language()))
    src = b'using CdecRules\n@locked @inline function f(x::Int)\n    return x\nend\n'
    tree = parser.parse(src)
    assert using_has_shim(tree.root_node, src)
    call = tree.root_node.named_children[-1]
    assert foreign_macros(call, src, True) == ["@inline"]


def test_shim_file_is_not_parsed_as_a_class(tmp_path):
    (tmp_path / "CdecRules.jl").write_text(
        "module CdecRules\nmacro sealed(a...) esc(a[end]) end\nend\n", encoding="utf-8"
    )
    (tmp_path / "real.jl").write_text("struct Thing\n    x::Int\nend\n", encoding="utf-8")
    parsed = parse_project(tmp_path)
    assert [c.name for c in parsed.iter_classes()] == ["Thing"]
