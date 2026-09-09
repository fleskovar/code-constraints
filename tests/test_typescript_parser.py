"""Parse the typescript_demo fixture and assert the resulting model."""

from __future__ import annotations

from pathlib import Path

from code_constraints.core.associations import resolve_association
from code_constraints.core.model import Visibility
from code_constraints.typescript import parse_project

FIXTURE = Path(__file__).parent / "fixtures" / "typescript_demo"


def _find_class(project, qualified_name):
    return next(c for c in project.iter_classes() if c.qualified_name == qualified_name)


def test_directory_layout_becomes_packages() -> None:
    project = parse_project(FIXTURE)
    qns: set[str] = set()

    def walk(pkgs):
        for p in pkgs:
            qns.add(p.qualified_name)
            walk(p.sub_packages)

    walk(project.packages)
    assert "zoo" in qns
    assert "zoo.animals" in qns
    assert "zoo.store" in qns


def test_abstract_class_detected() -> None:
    project = parse_project(FIXTURE)
    animal = _find_class(project, "zoo.animals.Animal")
    assert animal.kind == "abstract"


def test_class_extends_appears_as_base() -> None:
    project = parse_project(FIXTURE)
    dog = _find_class(project, "zoo.animals.Dog")
    assert "Animal" in dog.bases


def test_visibility_from_keyword_and_underscore_fallback() -> None:
    project = parse_project(FIXTURE)
    animal = _find_class(project, "zoo.animals.Animal")
    legs = next(a for a in animal.attributes if a.name == "legs")
    assert legs.visibility == Visibility.PROTECTED

    cart = _find_class(project, "zoo.store.Cart")
    items = next(a for a in cart.attributes if a.name == "items")
    assert items.visibility == Visibility.PRIVATE


def test_field_types_and_modifiers() -> None:
    project = parse_project(FIXTURE)
    cart = _find_class(project, "zoo.store.Cart")
    tax = next(a for a in cart.attributes if a.name == "taxRate")
    assert tax.type == "number"
    assert tax.is_static
    assert tax.default == "0.08"

    currency = next(a for a in cart.attributes if a.name == "currency")
    assert currency.is_readonly
    assert currency.type == "string"


def test_method_signatures_and_parameters() -> None:
    project = parse_project(FIXTURE)
    animal = _find_class(project, "zoo.animals.Animal")
    ctor = next(o for o in animal.operations if o.name == "constructor")
    legs = next(p for p in ctor.parameters if p.name == "legs")
    assert legs.type == "number"
    assert legs.default == "4"

    speak = next(o for o in animal.operations if o.name == "speak")
    assert speak.return_type == "string"
    assert speak.is_abstract


def test_interface_declared_as_interface_kind() -> None:
    project = parse_project(FIXTURE)
    iface = _find_class(project, "zoo.store.IPayment")
    assert iface.kind == "interface"
    charge = next(o for o in iface.operations if o.name == "charge")
    assert charge.return_type == "boolean"


def test_enum_members_become_static_attributes() -> None:
    project = parse_project(FIXTURE)
    currency = _find_class(project, "zoo.store.Currency")
    assert currency.kind == "enum"
    names = {a.name for a in currency.attributes}
    assert names == {"USD", "EUR", "GBP"}
    assert all(a.is_static for a in currency.attributes)


def test_type_alias_lands_as_interface_with_alias_attribute() -> None:
    project = parse_project(FIXTURE)
    money = _find_class(project, "zoo.store.Money")
    assert money.kind == "interface"
    alias = next(a for a in money.attributes if a.name == "_alias")
    assert "amount" in alias.type
    assert "currency" in alias.type


def test_association_resolves_through_collection_wrapper() -> None:
    project = parse_project(FIXTURE)
    cart = _find_class(project, "zoo.store.Cart")
    items = next(a for a in cart.attributes if a.name == "items")
    target, mult = resolve_association(items.type, project)
    assert target == "zoo.animals.Animal"
    assert mult == "*"


def test_jsdoc_summary_becomes_class_description() -> None:
    project = parse_project(FIXTURE)
    animal = _find_class(project, "zoo.animals.Animal")
    assert animal.description is not None
    assert "menagerie" in animal.description


def test_jsdoc_summary_becomes_method_description() -> None:
    project = parse_project(FIXTURE)
    animal = _find_class(project, "zoo.animals.Animal")
    speak = next(o for o in animal.operations if o.name == "speak")
    assert speak.description is not None
    assert "sound" in speak.description
