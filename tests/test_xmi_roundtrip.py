"""Round-trip a hand-built Project through XMI and back."""

from __future__ import annotations

from pathlib import Path

from code_constraints.core.model import (
    Activity,
    ActivityEdge,
    ActivityNode,
    Association,
    Attribute,
    Class,
    DiffStatus,
    EdgeLayout,
    Layout,
    Lifeline,
    Message,
    Operation,
    Package,
    Parameter,
    Project,
    Sequence,
    SourceLocation,
    Visibility,
)
from code_constraints.core.xmi_reader import read_project
from code_constraints.core.xmi_writer import write_project


def _sample_project() -> Project:
    animal = Class(
        name="Animal",
        qualified_name="zoo.Animal",
        kind="class",
        attributes=[
            Attribute(name="name", type="str", visibility=Visibility.PUBLIC),
            Attribute(name="legs", type="int", visibility=Visibility.PROTECTED),
        ],
        operations=[
            Operation(
                name="speak",
                parameters=[Parameter(name="self", type="Animal")],
                return_type="str",
            )
        ],
        location=SourceLocation(file="zoo/animal.py", start_line=1, end_line=20),
    )
    dog = Class(
        name="Dog",
        qualified_name="zoo.Dog",
        kind="class",
        bases=["zoo.Animal"],
        operations=[Operation(name="bark", return_type="None")],
    )
    pkg = Package(name="zoo", qualified_name="zoo", classes=[animal, dog])

    activity = Activity(
        name="feed",
        nodes=[
            ActivityNode(id="n1", kind="initial"),
            ActivityNode(id="n2", kind="action", label="pick food"),
            ActivityNode(id="n3", kind="final"),
        ],
        edges=[
            ActivityEdge(source="n1", target="n2"),
            ActivityEdge(source="n2", target="n3"),
        ],
        granularity="control-flow",
    )

    sequence = Sequence(
        name="checkout",
        lifelines=[Lifeline(name="user"), Lifeline(name="cart")],
        messages=[Message(sender="user", receiver="cart", label="add()")],
    )

    return Project(
        source_language="python",
        packages=[pkg],
        activities=[activity],
        sequences=[sequence],
        root_path="/fake/root",
    )


def test_roundtrip_preserves_model(tmp_path: Path) -> None:
    original = _sample_project()
    out = write_project(original, tmp_path / "p.xmi")
    assert out.exists()

    loaded = read_project(out)

    assert loaded.source_language == "python"
    assert loaded.root_path == "/fake/root"
    assert len(loaded.packages) == 1
    zoo = loaded.packages[0]
    assert zoo.qualified_name == "zoo"
    assert [c.name for c in zoo.classes] == ["Animal", "Dog"]

    animal = zoo.classes[0]
    assert [a.name for a in animal.attributes] == ["name", "legs"]
    assert animal.attributes[1].visibility == Visibility.PROTECTED
    assert animal.operations[0].return_type == "str"

    dog = zoo.classes[1]
    assert dog.bases == ["zoo.Animal"]

    assert len(loaded.activities) == 1
    act = loaded.activities[0]
    assert [n.kind for n in act.nodes] == ["initial", "action", "final"]
    assert act.edges[0].source == "n1"

    assert len(loaded.sequences) == 1
    seq = loaded.sequences[0]
    assert seq.messages[0].label == "add()"


def test_namespaces_present(tmp_path: Path) -> None:
    out = write_project(_sample_project(), tmp_path / "p.xmi")
    text = out.read_text(encoding="utf-8")
    assert "xmi:XMI" in text
    assert "uml:Model" in text
    assert "cdec:status" in text  # diff-namespace attribute is emitted


def test_layout_round_trips(tmp_path: Path) -> None:
    """v2 schema: layout coordinates survive serialise → deserialise."""
    cls = Class(
        name="Foo",
        qualified_name="lib.Foo",
        layout=Layout(x=120.0, y=80.5, width=200, height=140, collapsed=False),
    )
    pkg = Package(
        name="lib",
        qualified_name="lib",
        classes=[cls],
        layout=Layout(x=20, y=20, width=400, height=300),
    )
    act = Activity(
        name="boot",
        nodes=[
            ActivityNode(id="n1", kind="initial", layout=Layout(x=50, y=10, width=20, height=20)),
            ActivityNode(id="n2", kind="action", label="go", layout=Layout(x=50, y=80, width=80, height=40)),
        ],
        edges=[
            ActivityEdge(
                source="n1",
                target="n2",
                edge_layout=EdgeLayout(waypoints=[(60.0, 30.0), (60.0, 80.0)]),
            ),
        ],
    )
    seq = Sequence(
        name="boot_seq",
        lifelines=[Lifeline(name="ui", column_x=10.0), Lifeline(name="svc", column_x=200.0)],
    )

    project = Project(
        source_language="python",
        packages=[pkg],
        activities=[act],
        sequences=[seq],
    )

    out = write_project(project, tmp_path / "layout.xmi")
    loaded = read_project(out)

    loaded_pkg = loaded.packages[0]
    assert loaded_pkg.layout is not None
    assert (loaded_pkg.layout.x, loaded_pkg.layout.y) == (20, 20)

    loaded_cls = loaded_pkg.classes[0]
    assert loaded_cls.layout is not None
    assert loaded_cls.layout.x == 120.0
    assert loaded_cls.layout.y == 80.5  # non-integer survives
    assert loaded_cls.layout.width == 200
    assert loaded_cls.layout.height == 140

    loaded_act = loaded.activities[0]
    assert loaded_act.nodes[0].layout is not None
    assert (loaded_act.nodes[1].layout.x, loaded_act.nodes[1].layout.y) == (50, 80)
    assert loaded_act.edges[0].edge_layout is not None
    assert loaded_act.edges[0].edge_layout.waypoints == [(60.0, 30.0), (60.0, 80.0)]

    loaded_seq = loaded.sequences[0]
    assert loaded_seq.lifelines[0].column_x == 10.0
    assert loaded_seq.lifelines[1].column_x == 200.0


def test_explicit_associations_round_trip(tmp_path: Path) -> None:
    """Editor-authored Associations survive write -> read."""
    a = Class(name="A", qualified_name="lib.A")
    b = Class(name="B", qualified_name="lib.B")
    pkg = Package(name="lib", qualified_name="lib", classes=[a, b])
    project = Project(
        source_language="python",
        packages=[pkg],
        associations=[
            Association(
                source="lib.A",
                target="lib.B",
                name="owns",
                source_multiplicity="1",
                target_multiplicity="*",
                source_role="owner",
                target_role="items",
            ),
        ],
    )

    out = write_project(project, tmp_path / "assoc.xmi")
    loaded = read_project(out)

    assert len(loaded.associations) == 1
    got = loaded.associations[0]
    assert got.source == "lib.A"
    assert got.target == "lib.B"
    assert got.name == "owns"
    assert got.source_multiplicity == "1"
    assert got.target_multiplicity == "*"
    assert got.source_role == "owner"
    assert got.target_role == "items"


def test_descriptions_round_trip_as_owned_comments(tmp_path: Path) -> None:
    """Standards-compliant uml:Comment elements should survive write -> read,
    and the XMI text should contain `<ownedComment xmi:type="uml:Comment">`
    children (UML 2.x standard) rather than any project-private encoding."""
    animal = Class(
        name="Animal",
        qualified_name="zoo.Animal",
        kind="class",
        description="Abstract base class for every creature.",
        attributes=[
            Attribute(
                name="legs",
                type="int",
                visibility=Visibility.PUBLIC,
                description="Number of legs the animal walks on.",
            ),
        ],
        operations=[
            Operation(
                name="speak",
                return_type="str",
                description="Return the sound this animal makes.",
            )
        ],
    )
    pkg = Package(
        name="zoo",
        qualified_name="zoo",
        classes=[animal],
        description="Top-level zoo package.",
    )
    project = Project(source_language="python", packages=[pkg])

    out = write_project(project, tmp_path / "docs.xmi")
    text = out.read_text(encoding="utf-8")
    # Must be standards-compliant — no private extension namespace for descriptions.
    assert 'ownedComment' in text
    assert 'xmi:type="uml:Comment"' in text
    assert "Abstract base class for every creature." in text

    loaded = read_project(out)
    loaded_pkg = loaded.packages[0]
    assert loaded_pkg.description == "Top-level zoo package."
    loaded_animal = loaded_pkg.classes[0]
    assert loaded_animal.description == "Abstract base class for every creature."
    assert loaded_animal.attributes[0].description == "Number of legs the animal walks on."
    assert loaded_animal.operations[0].description == "Return the sound this animal makes."


def test_description_xmi_ids_are_deterministic(tmp_path: Path) -> None:
    """Re-emitting the same project must produce byte-identical XMI so
    description ids don't churn between parses."""
    proj = Project(
        source_language="python",
        packages=[
            Package(
                name="lib",
                qualified_name="lib",
                description="root",
                classes=[
                    Class(
                        name="A",
                        qualified_name="lib.A",
                        description="class A",
                        attributes=[Attribute(name="x", type="int", description="x doc")],
                        operations=[Operation(name="go", return_type="str", description="go doc")],
                    )
                ],
            )
        ],
    )
    first = write_project(proj, tmp_path / "a.xmi").read_bytes()
    second = write_project(proj, tmp_path / "b.xmi").read_bytes()
    assert first == second


def test_missing_description_emits_no_comment(tmp_path: Path) -> None:
    """A None description must not emit an empty ownedComment element."""
    proj = Project(
        source_language="python",
        packages=[
            Package(
                name="lib",
                qualified_name="lib",
                classes=[Class(name="A", qualified_name="lib.A")],
            )
        ],
    )
    out = write_project(proj, tmp_path / "x.xmi")
    text = out.read_text(encoding="utf-8")
    assert "ownedComment" not in text


def test_missing_layout_loads_as_none(tmp_path: Path) -> None:
    """Backwards compat: pre-v2 XMIs (no layout attrs) load with layout=None."""
    project = _sample_project()  # nothing in this sample carries layout
    out = write_project(project, tmp_path / "no-layout.xmi")
    loaded = read_project(out)
    assert loaded.packages[0].classes[0].layout is None
    assert loaded.activities[0].nodes[0].layout is None
    assert loaded.activities[0].edges[0].edge_layout is None
    assert loaded.sequences[0].lifelines[0].column_x is None


def test_class_dependencies_round_trip(tmp_path: Path) -> None:
    """Body-derived `Class.dependencies` survive write -> read."""
    cls = Class(
        name="Caller",
        qualified_name="pkg.Caller",
        dependencies=["ControlUtils", "Helper"],
    )
    proj = Project(
        source_language="csharp",
        packages=[Package(name="pkg", qualified_name="pkg", classes=[cls])],
    )
    out = tmp_path / "deps.xmi"
    write_project(proj, out)
    loaded = read_project(out)
    loaded_cls = next(c for c in loaded.iter_classes() if c.qualified_name == "pkg.Caller")
    assert loaded_cls.dependencies == ["ControlUtils", "Helper"]


def test_missing_dependencies_load_as_empty(tmp_path: Path) -> None:
    """Pre-existing XMI without dependency elements loads as an empty list."""
    cls = Class(name="Plain", qualified_name="pkg.Plain")
    proj = Project(
        source_language="csharp",
        packages=[Package(name="pkg", qualified_name="pkg", classes=[cls])],
    )
    out = tmp_path / "plain.xmi"
    write_project(proj, out)
    loaded = read_project(out)
    loaded_cls = next(c for c in loaded.iter_classes() if c.qualified_name == "pkg.Plain")
    assert loaded_cls.dependencies == []
