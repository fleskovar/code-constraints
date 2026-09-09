"""Sanity-check DOT emission. We don't render here (no `dot` binary needed in CI),
just verify the emitted DSL has the expected structure and diff styling."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from code_constraints.core.diff import diff_projects
from code_constraints.core.dot import (
    emit_activity_diagram,
    emit_class_diagram,
    emit_package_diagram,
    emit_sequence_diagram,
)
from code_constraints.core.model import Attribute, Class, Package, Project, Visibility
from code_constraints.python import parse_project

FIXTURE = Path(__file__).parent / "fixtures" / "python_demo"


def test_class_diagram_is_a_digraph() -> None:
    project = parse_project(FIXTURE)
    text = emit_class_diagram(project)
    assert text.startswith('digraph "class"')
    assert text.rstrip().endswith("}")
    # Both classes show up as record-table labels by qualified id
    assert "animals_Animal" in text
    assert "animals_Dog" in text
    # Class header / name
    assert "<B>Animal</B>" in text
    assert "<B>Dog</B>" in text


def test_class_diagram_renders_inheritance() -> None:
    project = parse_project(FIXTURE)
    text = emit_class_diagram(project)
    # UML generalization == empty-triangle arrowhead from child to parent
    assert "arrowhead=empty" in text
    assert '"animals_Dog" -> "animals_Animal"' in text


def test_class_diagram_diff_uses_green_and_red() -> None:
    base = parse_project(FIXTURE)
    new = deepcopy(base)
    dog = next(c for c in new.iter_classes() if c.qualified_name == "animals.Dog")
    dog.attributes.append(Attribute(name="age", type="int", visibility=Visibility.PUBLIC))
    cart = next(c for c in new.iter_classes() if c.qualified_name == "store.Cart")
    cart.operations = [op for op in cart.operations if op.name != "format_receipt"]

    diff = diff_projects(base, new)
    text = emit_class_diagram(diff)
    # Added attribute -> dark green text, light green cell background
    assert "darkgreen" in text
    assert "age" in text
    assert "#DAF7DC" in text
    # Removed operation -> red, strikethrough, light red cell background
    assert "red" in text
    assert "<S>" in text
    assert "#FBD7D7" in text


def test_package_diagram_uses_clusters() -> None:
    project = parse_project(FIXTURE)
    text = emit_package_diagram(project)
    assert "subgraph cluster_animals" in text
    assert "subgraph cluster_store" in text
    assert 'label="animals"' in text


def test_activity_emit_for_dog_speak() -> None:
    project = parse_project(FIXTURE)
    act = next(a for a in project.activities if a.name == "dog_speak")
    text = emit_activity_diagram(act)
    assert text.startswith('digraph "activity"')
    # initial / final node shapes
    assert "shape=circle" in text
    assert "shape=doublecircle" in text
    # decision diamond from the if-elif-else
    assert "shape=diamond" in text


def test_class_typed_field_creates_association_edge() -> None:
    """A class field whose type points to another project class should emit
    an association edge (arrowhead=vee), with multiplicity "*" for arrays/lists."""
    snapshot = Class(name="StateSnapshot", qualified_name="sim.StateSnapshot")
    window = Class(
        name="StateWindow",
        qualified_name="sim.StateWindow",
        attributes=[
            Attribute(name="_buffer", type="StateSnapshot[]", visibility=Visibility.PRIVATE),
            Attribute(name="_pending", type="List<StateSnapshot>", visibility=Visibility.PRIVATE),
            Attribute(name="_latest", type="StateSnapshot", visibility=Visibility.PRIVATE),
        ],
    )
    project = Project(
        source_language="csharp",
        packages=[Package(name="sim", qualified_name="sim", classes=[snapshot, window])],
    )
    text = emit_class_diagram(project)

    # Exactly one association edge per (source, target) pair, even though three
    # different fields reference StateSnapshot.
    edge = '"sim_StateWindow" -> "sim_StateSnapshot"'
    assert edge in text
    assert text.count(edge) == 1
    # Collections promote multiplicity to "*", which wins over the singular field.
    assert 'headlabel="*"' in text
    # Association edges use the open arrowhead (UML "directed association"),
    # distinct from the inheritance empty-triangle.
    assert "arrowhead=vee" in text


def test_association_does_not_duplicate_inheritance() -> None:
    """If A inherits from B AND has a B-typed field, only the inheritance edge
    is emitted — we don't want a redundant association on the same pair."""
    base = Class(name="Base", qualified_name="m.Base")
    derived = Class(
        name="Derived",
        qualified_name="m.Derived",
        bases=["Base"],
        attributes=[Attribute(name="parent", type="Base")],
    )
    project = Project(
        source_language="python",
        packages=[Package(name="m", qualified_name="m", classes=[base, derived])],
    )
    text = emit_class_diagram(project)
    # The pair appears once, and the edge uses the inheritance arrowhead.
    pair = '"m_Derived" -> "m_Base"'
    assert text.count(pair) == 1
    assert f"{pair} [arrowhead=empty]" in text


def test_association_skips_self_reference() -> None:
    """A field whose type is the enclosing class shouldn't create a self-loop."""
    node = Class(
        name="Node",
        qualified_name="tree.Node",
        attributes=[Attribute(name="next", type="Node")],
    )
    project = Project(
        source_language="python",
        packages=[Package(name="tree", qualified_name="tree", classes=[node])],
    )
    text = emit_class_diagram(project)
    assert '"tree_Node" -> "tree_Node"' not in text


def test_association_ignores_primitives_and_external_types() -> None:
    """Edges should only be drawn between two project classes — primitives and
    third-party types (like Unity's Vector3) must not produce spurious edges."""
    foo = Class(
        name="Foo",
        qualified_name="m.Foo",
        attributes=[
            Attribute(name="count", type="int"),
            Attribute(name="pos", type="Vector3"),  # not in project
            Attribute(name="name", type="string"),
        ],
    )
    project = Project(
        source_language="csharp",
        packages=[Package(name="m", qualified_name="m", classes=[foo])],
    )
    text = emit_class_diagram(project)
    assert "arrowhead=vee" not in text  # no association edges at all


def test_sequence_emit_for_checkout() -> None:
    project = parse_project(FIXTURE)
    seq = next(s for s in project.sequences if s.name == "checkout_flow")
    text = emit_sequence_diagram(seq)
    # header row contains every lifeline as a *_head node
    assert "_head" in text
    # actual message labels are rendered as edge labels
    assert "authorize()" in text
    assert "capture()" in text
    # lifelines drawn as dashed vertical edges
    assert "style=dashed" in text
