"""Diff engine: ensure added/removed/changed are correctly populated."""

from __future__ import annotations

from copy import deepcopy

from code_constraints.core.diff import diff_projects
from code_constraints.core.model import (
    Activity,
    ActivityEdge,
    ActivityNode,
    Attribute,
    Class,
    DiffStatus,
    Lifeline,
    Message,
    Operation,
    Package,
    Parameter,
    Project,
    Sequence,
    Visibility,
)


def _base() -> Project:
    animal = Class(
        name="Animal",
        qualified_name="zoo.Animal",
        attributes=[
            Attribute(name="name", type="str"),
            Attribute(name="legs", type="int"),
        ],
        operations=[Operation(name="speak", return_type="str")],
    )
    return Project(
        source_language="python",
        packages=[Package(name="zoo", qualified_name="zoo", classes=[animal])],
    )


def test_added_attribute_is_marked_added() -> None:
    old = _base()
    new = deepcopy(old)
    new.packages[0].classes[0].attributes.append(Attribute(name="age", type="int"))

    diff = diff_projects(old, new)
    cls = diff.packages[0].classes[0]
    statuses = {a.name: a.status for a in cls.attributes}
    assert statuses["age"] == DiffStatus.ADDED
    assert statuses["name"] == DiffStatus.UNCHANGED
    assert cls.status == DiffStatus.CHANGED
    assert diff.packages[0].status == DiffStatus.CHANGED


def test_removed_attribute_is_kept_with_removed_status() -> None:
    old = _base()
    new = deepcopy(old)
    new.packages[0].classes[0].attributes = [
        a for a in new.packages[0].classes[0].attributes if a.name != "legs"
    ]

    diff = diff_projects(old, new)
    cls = diff.packages[0].classes[0]
    names = [a.name for a in cls.attributes]
    assert "legs" in names  # ghost attribute kept for strikethrough rendering
    statuses = {a.name: a.status for a in cls.attributes}
    assert statuses["legs"] == DiffStatus.REMOVED


def test_added_class_marks_entire_subtree() -> None:
    old = _base()
    new = deepcopy(old)
    new.packages[0].classes.append(
        Class(
            name="Dog",
            qualified_name="zoo.Dog",
            attributes=[Attribute(name="breed", type="str")],
        )
    )

    diff = diff_projects(old, new)
    dog = next(c for c in diff.packages[0].classes if c.name == "Dog")
    assert dog.status == DiffStatus.ADDED
    assert all(a.status == DiffStatus.ADDED for a in dog.attributes)


def test_removed_package_is_kept_marked_removed() -> None:
    old = _base()
    old.packages.append(Package(name="legacy", qualified_name="legacy"))
    new = deepcopy(old)
    new.packages = [p for p in new.packages if p.qualified_name != "legacy"]

    diff = diff_projects(old, new)
    legacy = next(p for p in diff.packages if p.qualified_name == "legacy")
    assert legacy.status == DiffStatus.REMOVED


def test_unchanged_project_reports_unchanged() -> None:
    old = _base()
    new = deepcopy(old)
    diff = diff_projects(old, new)
    assert diff.packages[0].status == DiffStatus.UNCHANGED
    assert diff.packages[0].classes[0].status == DiffStatus.UNCHANGED


def _activity_project(nodes: list[ActivityNode], edges: list[ActivityEdge]) -> Project:
    return Project(
        source_language="python",
        activities=[Activity(name="flow", nodes=nodes, edges=edges)],
    )


def test_activity_added_node_marked_added_others_unchanged() -> None:
    old_nodes = [
        ActivityNode(id="a0", kind="initial"),
        ActivityNode(id="a1", kind="action", label="step1"),
        ActivityNode(id="a2", kind="final"),
    ]
    old_edges = [
        ActivityEdge(source="a0", target="a1"),
        ActivityEdge(source="a1", target="a2"),
    ]
    new_nodes = [
        ActivityNode(id="b0", kind="initial"),
        ActivityNode(id="b1", kind="action", label="step1"),
        ActivityNode(id="b2", kind="action", label="step2"),
        ActivityNode(id="b3", kind="final"),
    ]
    new_edges = [
        ActivityEdge(source="b0", target="b1"),
        ActivityEdge(source="b1", target="b2"),
        ActivityEdge(source="b2", target="b3"),
    ]
    diff = diff_projects(
        _activity_project(old_nodes, old_edges),
        _activity_project(new_nodes, new_edges),
    )
    act = diff.activities[0]
    assert act.status == DiffStatus.CHANGED
    by_label = {(n.kind, n.label): n.status for n in act.nodes}
    assert by_label[("action", "step1")] == DiffStatus.UNCHANGED
    assert by_label[("action", "step2")] == DiffStatus.ADDED
    assert by_label[("initial", "")] == DiffStatus.UNCHANGED


def test_activity_removed_edge_kept_as_ghost() -> None:
    nodes = [
        ActivityNode(id="a0", kind="initial"),
        ActivityNode(id="a1", kind="action", label="x"),
        ActivityNode(id="a2", kind="final"),
    ]
    old_edges = [
        ActivityEdge(source="a0", target="a1"),
        ActivityEdge(source="a1", target="a2"),
    ]
    new_edges = [ActivityEdge(source="a0", target="a2")]
    diff = diff_projects(
        _activity_project(nodes, old_edges),
        _activity_project(nodes, new_edges),
    )
    act = diff.activities[0]
    statuses = sorted(e.status.value for e in act.edges)
    # one ADDED (a0->a2), two REMOVED (a0->a1, a1->a2)
    assert statuses == ["added", "removed", "removed"]
    assert act.status == DiffStatus.CHANGED


def test_unchanged_activity_reports_unchanged() -> None:
    nodes = [
        ActivityNode(id="a0", kind="initial"),
        ActivityNode(id="a1", kind="final"),
    ]
    edges = [ActivityEdge(source="a0", target="a1")]
    diff = diff_projects(
        _activity_project(nodes, edges),
        _activity_project(nodes, edges),
    )
    act = diff.activities[0]
    assert act.status == DiffStatus.UNCHANGED
    assert all(n.status == DiffStatus.UNCHANGED for n in act.nodes)
    assert all(e.status == DiffStatus.UNCHANGED for e in act.edges)


def test_description_only_change_does_not_flag_changed() -> None:
    """Decision locked: descriptions are content but not structural drift."""
    old = _base()
    old.packages[0].classes[0].description = "old class doc"
    old.packages[0].classes[0].attributes[0].description = "old attr doc"
    old.packages[0].classes[0].operations[0].description = "old op doc"
    new = deepcopy(old)
    new.packages[0].classes[0].description = "NEW class doc"
    new.packages[0].classes[0].attributes[0].description = "NEW attr doc"
    new.packages[0].classes[0].operations[0].description = "NEW op doc"

    diff = diff_projects(old, new)
    pkg = diff.packages[0]
    cls = pkg.classes[0]
    assert pkg.status == DiffStatus.UNCHANGED
    assert cls.status == DiffStatus.UNCHANGED
    assert all(a.status == DiffStatus.UNCHANGED for a in cls.attributes)
    assert all(o.status == DiffStatus.UNCHANGED for o in cls.operations)
    # The new descriptions win on the merged result.
    assert cls.description == "NEW class doc"
    assert cls.attributes[0].description == "NEW attr doc"
    assert cls.operations[0].description == "NEW op doc"


def test_attribute_type_change_shows_as_remove_plus_add() -> None:
    """Same name, different type: signature() differs, so it shows as a pair."""
    old = _base()
    new = deepcopy(old)
    new.packages[0].classes[0].attributes[1].type = "float"  # legs: int -> float

    diff = diff_projects(old, new)
    legs_entries = [a for a in diff.packages[0].classes[0].attributes if a.name == "legs"]
    assert len(legs_entries) == 2
    statuses = sorted(a.status.value for a in legs_entries)
    assert statuses == ["added", "removed"]
