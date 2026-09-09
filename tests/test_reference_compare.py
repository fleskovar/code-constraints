"""Reference gate: `compare_to_reference` must flag every structural deviation.

Unlike `diff_projects`, this comparator must also catch visibility/modifier
changes and class-kind changes, which the signature-based diff is blind to.
"""

from __future__ import annotations

from copy import deepcopy

import pytest

from code_constraints.core.model import (
    Attribute,
    Class,
    Operation,
    Package,
    Parameter,
    Project,
    Visibility,
)
from code_constraints.reference import compare_to_reference


def _base() -> Project:
    animal = Class(
        name="Animal",
        qualified_name="zoo.Animal",
        kind="class",
        bases=["object"],
        attributes=[
            Attribute(name="name", type="str", visibility=Visibility.PUBLIC),
            Attribute(name="legs", type="int"),
        ],
        operations=[
            Operation(
                name="speak",
                parameters=[Parameter(name="self", type="")],
                return_type="str",
                visibility=Visibility.PUBLIC,
            )
        ],
    )
    return Project(
        source_language="python",
        packages=[Package(name="zoo", qualified_name="zoo", classes=[animal])],
    )


def _categories(devs) -> set[str]:
    return {d.category for d in devs}


def _cls(proj: Project) -> Class:
    return proj.packages[0].classes[0]


def test_identical_projects_have_no_deviations() -> None:
    assert compare_to_reference(_base(), deepcopy(_base())) == []


def test_added_and_removed_class() -> None:
    new = deepcopy(_base())
    new.packages[0].classes.append(
        Class(name="Plant", qualified_name="zoo.Plant")
    )
    devs = compare_to_reference(_base(), new)
    assert _categories(devs) == {"class-added"}
    assert devs[0].qualified_name == "zoo.Plant"

    devs_removed = compare_to_reference(new, _base())
    assert _categories(devs_removed) == {"class-removed"}


def test_added_and_removed_attribute() -> None:
    new = deepcopy(_base())
    _cls(new).attributes.append(Attribute(name="age", type="int"))
    assert _categories(compare_to_reference(_base(), new)) == {"attribute-added"}
    assert _categories(compare_to_reference(new, _base())) == {"attribute-removed"}


def test_added_and_removed_operation() -> None:
    new = deepcopy(_base())
    _cls(new).operations.append(Operation(name="eat", return_type="None"))
    assert _categories(compare_to_reference(_base(), new)) == {"operation-added"}
    assert _categories(compare_to_reference(new, _base())) == {"operation-removed"}


def test_attribute_type_change() -> None:
    new = deepcopy(_base())
    _cls(new).attributes[1].type = "float"
    devs = compare_to_reference(_base(), new)
    assert _categories(devs) == {"attribute-changed"}
    assert "type" in devs[0].message


def test_attribute_visibility_change_is_detected() -> None:
    new = deepcopy(_base())
    _cls(new).attributes[0].visibility = Visibility.PRIVATE
    devs = compare_to_reference(_base(), new)
    assert _categories(devs) == {"attribute-changed"}
    assert "access level" in devs[0].message


def test_attribute_static_change_is_detected() -> None:
    new = deepcopy(_base())
    _cls(new).attributes[0].is_static = True
    devs = compare_to_reference(_base(), new)
    assert _categories(devs) == {"attribute-changed"}
    assert "static" in devs[0].message


def test_operation_return_type_change() -> None:
    new = deepcopy(_base())
    _cls(new).operations[0].return_type = "int"
    devs = compare_to_reference(_base(), new)
    assert _categories(devs) == {"operation-return-type-changed"}


def test_operation_signature_change() -> None:
    new = deepcopy(_base())
    _cls(new).operations[0].parameters.append(Parameter(name="loudly", type="bool"))
    devs = compare_to_reference(_base(), new)
    assert _categories(devs) == {"operation-signature-changed"}


def test_operation_modifier_changes_are_detected() -> None:
    new = deepcopy(_base())
    op = _cls(new).operations[0]
    op.is_static = True
    op.is_abstract = True
    op.visibility = Visibility.PROTECTED
    devs = compare_to_reference(_base(), new)
    assert _categories(devs) == {"operation-modifier-changed"}
    msg = devs[0].message
    assert "static" in msg and "abstract" in msg and "access level" in msg


def test_class_kind_change_is_detected() -> None:
    new = deepcopy(_base())
    _cls(new).kind = "abstract"
    devs = compare_to_reference(_base(), new)
    assert _categories(devs) == {"class-kind-changed"}
    assert devs[0].old == "class" and devs[0].new == "abstract"


def test_class_bases_change_is_detected() -> None:
    new = deepcopy(_base())
    _cls(new).bases = ["object", "Mammal"]
    devs = compare_to_reference(_base(), new)
    assert _categories(devs) == {"class-bases-changed"}


def test_language_mismatch_raises() -> None:
    ref = _base()
    cur = deepcopy(_base())
    cur.source_language = "csharp"
    with pytest.raises(ValueError):
        compare_to_reference(ref, cur)
