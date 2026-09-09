"""Sanity-check the SvelteFlow JSON graph builders.

The web canvas is keyed by `Class.stable_id()`. Duplicate ids (e.g. C# partial
classes sharing a qualified name) would crash the canvas with
`each_key_duplicate` in Svelte and "duplicate node id" in xyflow. We dedupe at
the backend boundary; this test pins that behaviour.
"""

from __future__ import annotations

from code_constraints.core.diff import diff_projects
from code_constraints.core.graph_model import (
    build_activity_change_list,
    build_activity_graph,
    build_change_list,
    build_class_graph,
    build_package_graph,
    build_sequence_change_list,
    build_sequence_graph,
)
from code_constraints.core.model import (
    Activity,
    ActivityEdge,
    ActivityNode,
    Attribute,
    Class,
    Lifeline,
    Message,
    Operation,
    Package,
    Parameter,
    Project,
    Sequence,
)


def _make_project_with_duplicate_qname() -> Project:
    """Two classes with the same qualified_name — simulates a C# partial."""
    cls_a = Class(name="Foo", qualified_name="pkg.Foo")
    cls_b = Class(
        name="Foo",
        qualified_name="pkg.Foo",
        attributes=[Attribute(name="x", type="int")],
    )
    pkg = Package(name="pkg", qualified_name="pkg", classes=[cls_a, cls_b])
    return Project(source_language="python", packages=[pkg])


def test_class_graph_dedupes_duplicate_stable_ids() -> None:
    proj = _make_project_with_duplicate_qname()
    graph = build_class_graph(proj)
    ids = [n["id"] for n in graph["nodes"]]
    assert len(ids) == len(set(ids)), f"duplicate node ids: {ids}"


def test_package_graph_dedupes_duplicate_stable_ids() -> None:
    proj = _make_project_with_duplicate_qname()
    graph = build_package_graph(proj)
    ids = [n["id"] for n in graph["nodes"]]
    assert len(ids) == len(set(ids)), f"duplicate node ids: {ids}"


def test_class_graph_basic_shape() -> None:
    """One inheritance edge, one association edge, no self-loops."""
    base = Class(name="Animal", qualified_name="animals.Animal")
    dog = Class(name="Dog", qualified_name="animals.Dog", bases=["Animal"])
    owner = Class(
        name="Owner",
        qualified_name="people.Owner",
        attributes=[Attribute(name="pet", type="Dog")],
    )
    proj = Project(
        source_language="python",
        packages=[
            Package(name="animals", qualified_name="animals", classes=[base, dog]),
            Package(name="people", qualified_name="people", classes=[owner]),
        ],
    )
    graph = build_class_graph(proj)
    kinds = sorted({e["kind"] for e in graph["edges"]})
    assert kinds == ["association", "inheritance"]
    assert len(graph["nodes"]) == 3


def test_change_list_empty_for_unchanged_project() -> None:
    proj = _make_project_with_duplicate_qname()
    assert build_change_list(proj) == []


def test_class_graph_exposes_descriptions() -> None:
    """The frontend reads `description` off each class/attribute/operation node."""
    cls = Class(
        name="Foo",
        qualified_name="pkg.Foo",
        description="A foo widget.",
        attributes=[Attribute(name="x", type="int", description="x doc")],
        operations=[Operation(name="go", return_type="str", description="go doc")],
    )
    proj = Project(
        source_language="python",
        packages=[Package(name="pkg", qualified_name="pkg", classes=[cls])],
    )
    graph = build_class_graph(proj)
    node = graph["nodes"][0]
    assert node["description"] == "A foo widget."
    assert node["attributes"][0]["description"] == "x doc"
    assert node["operations"][0]["description"] == "go doc"


def test_class_graph_null_descriptions_serialize_as_none() -> None:
    """Absent descriptions remain None so the frontend gets JSON null."""
    cls = Class(
        name="Bar",
        qualified_name="pkg.Bar",
        attributes=[Attribute(name="y", type="int")],
    )
    proj = Project(
        source_language="python",
        packages=[Package(name="pkg", qualified_name="pkg", classes=[cls])],
    )
    graph = build_class_graph(proj)
    node = graph["nodes"][0]
    assert node["description"] is None
    assert node["attributes"][0]["description"] is None


def test_package_graph_dependency_edges() -> None:
    """A class in package A whose attribute type is a class in package B
    should produce a single dependency edge A→B."""
    animal = Class(name="Animal", qualified_name="animals.Animal")
    dog = Class(name="Dog", qualified_name="animals.Dog", bases=["Animal"])
    owner = Class(
        name="Owner",
        qualified_name="people.Owner",
        attributes=[Attribute(name="pet", type="Dog")],
    )
    proj = Project(
        source_language="python",
        packages=[
            Package(name="animals", qualified_name="animals", classes=[animal, dog]),
            Package(name="people", qualified_name="people", classes=[owner]),
        ],
    )
    graph = build_package_graph(proj)
    qnames = sorted(n["qualifiedName"] for n in graph["nodes"])
    assert qnames == ["animals", "people"]

    # Exactly one dependency edge: people → animals (Owner.pet: Dog).
    assert len(graph["edges"]) == 1
    edge = graph["edges"][0]
    src_pkg = next(n["qualifiedName"] for n in graph["nodes"] if n["id"] == edge["source"])
    tgt_pkg = next(n["qualifiedName"] for n in graph["nodes"] if n["id"] == edge["target"])
    assert (src_pkg, tgt_pkg) == ("people", "animals")
    assert edge["kind"] == "dependency"


def test_package_graph_resolves_python_subscript_generics() -> None:
    """`list[Foo]`, `dict[str, Foo]`, and `Optional[Foo]` (Python 3.9+
    subscript generics) must resolve to Foo so association/dependency
    edges fire on Python codebases using modern type annotations."""
    item = Class(name="Item", qualified_name="catalog.Item")
    cart = Class(
        name="Cart",
        qualified_name="orders.Cart",
        attributes=[
            Attribute(name="items", type="list[Item]"),
            Attribute(name="lookup", type="dict[str, Item]"),
            Attribute(name="featured", type="Optional[Item]"),
        ],
    )
    proj = Project(
        source_language="python",
        packages=[
            Package(name="catalog", qualified_name="catalog", classes=[item]),
            Package(name="orders", qualified_name="orders", classes=[cart]),
        ],
    )
    graph = build_package_graph(proj)
    edges = graph["edges"]
    assert len(edges) == 1
    edge = edges[0]
    src_pkg = next(n["qualifiedName"] for n in graph["nodes"] if n["id"] == edge["source"])
    tgt_pkg = next(n["qualifiedName"] for n in graph["nodes"] if n["id"] == edge["target"])
    assert (src_pkg, tgt_pkg) == ("orders", "catalog")


def test_package_graph_no_self_loops() -> None:
    """Intra-package references must NOT produce self-loops."""
    a = Class(name="A", qualified_name="pkg.A")
    b = Class(
        name="B",
        qualified_name="pkg.B",
        bases=["A"],
        attributes=[Attribute(name="link", type="A")],
    )
    proj = Project(
        source_language="python",
        packages=[Package(name="pkg", qualified_name="pkg", classes=[a, b])],
    )
    graph = build_package_graph(proj)
    assert graph["edges"] == []


def test_package_graph_dedupes_multi_class_edges() -> None:
    """Two classes in A referencing two classes in B → one dependency edge."""
    b1 = Class(name="B1", qualified_name="b.B1")
    b2 = Class(name="B2", qualified_name="b.B2")
    a1 = Class(
        name="A1",
        qualified_name="a.A1",
        attributes=[Attribute(name="x", type="B1")],
    )
    a2 = Class(
        name="A2",
        qualified_name="a.A2",
        attributes=[Attribute(name="y", type="B2")],
    )
    proj = Project(
        source_language="python",
        packages=[
            Package(name="a", qualified_name="a", classes=[a1, a2]),
            Package(name="b", qualified_name="b", classes=[b1, b2]),
        ],
    )
    graph = build_package_graph(proj)
    assert len(graph["edges"]) == 1


def _seq_project(lifelines, messages) -> Project:
    return Project(
        source_language="python",
        sequences=[Sequence(name="flow", lifelines=lifelines, messages=messages)],
    )


def test_build_sequence_graph_basic_shape() -> None:
    proj = _seq_project(
        [Lifeline(name="self"), Lifeline(name="payment", represents="Payment")],
        [
            Message(sender="self", receiver="payment", label="authorize()"),
            Message(sender="self", receiver="payment", label="capture()"),
            Message(sender="payment", receiver="self", label="ok", is_return=True),
        ],
    )
    g = build_sequence_graph(proj, "flow")
    assert [ll["column"] for ll in g["lifelines"]] == [0, 1]
    assert [m["row"] for m in g["messages"]] == [0, 1, 2]
    # message endpoints reference lifeline ids in the graph
    ids = {ll["id"] for ll in g["lifelines"]}
    for m in g["messages"]:
        assert m["sender"] in ids
        assert m["receiver"] in ids
    assert g["messages"][2]["isReturn"] is True
    assert g["meta"]["lifelineCount"] == 2
    assert g["meta"]["messageCount"] == 3


def test_build_sequence_graph_missing_raises() -> None:
    proj = _seq_project([], [])
    try:
        build_sequence_graph(proj, "nope")
    except KeyError:
        return
    raise AssertionError("expected KeyError")


def test_activity_graph_carries_per_node_diff_status() -> None:
    old = Project(
        source_language="python",
        activities=[
            Activity(
                name="flow",
                nodes=[
                    ActivityNode(id="a0", kind="initial"),
                    ActivityNode(id="a1", kind="action", label="step"),
                    ActivityNode(id="a2", kind="final"),
                ],
                edges=[
                    ActivityEdge(source="a0", target="a1"),
                    ActivityEdge(source="a1", target="a2"),
                ],
            )
        ],
    )
    new = Project(
        source_language="python",
        activities=[
            Activity(
                name="flow",
                nodes=[
                    ActivityNode(id="b0", kind="initial"),
                    ActivityNode(id="b1", kind="action", label="step"),
                    ActivityNode(id="b2", kind="action", label="newstep"),
                    ActivityNode(id="b3", kind="final"),
                ],
                edges=[
                    ActivityEdge(source="b0", target="b1"),
                    ActivityEdge(source="b1", target="b2"),
                    ActivityEdge(source="b2", target="b3"),
                ],
            )
        ],
    )
    annotated = diff_projects(old, new)
    g = build_activity_graph(annotated, "flow")
    by_label = {(n["kind"], n["label"]): n["status"] for n in g["nodes"]}
    assert by_label[("action", "step")] == "unchanged"
    assert by_label[("action", "newstep")] == "added"


def test_build_activity_change_list_summary_and_members() -> None:
    old = Project(
        source_language="python",
        activities=[
            Activity(
                name="flow",
                nodes=[
                    ActivityNode(id="a0", kind="initial"),
                    ActivityNode(id="a1", kind="action", label="x"),
                    ActivityNode(id="a2", kind="final"),
                ],
                edges=[
                    ActivityEdge(source="a0", target="a1"),
                    ActivityEdge(source="a1", target="a2"),
                ],
            )
        ],
    )
    new = Project(
        source_language="python",
        activities=[
            Activity(
                name="flow",
                nodes=[
                    ActivityNode(id="b0", kind="initial"),
                    ActivityNode(id="b1", kind="action", label="x"),
                    ActivityNode(id="b2", kind="action", label="y"),
                    ActivityNode(id="b3", kind="final"),
                ],
                edges=[
                    ActivityEdge(source="b0", target="b1"),
                    ActivityEdge(source="b1", target="b2"),
                    ActivityEdge(source="b2", target="b3"),
                ],
            )
        ],
    )
    annotated = diff_projects(old, new)
    out = build_activity_change_list(annotated)
    assert len(out) == 1
    entry = out[0]
    assert entry["diagramKind"] == "activity"
    assert entry["kind"] == "changed"
    added_node = [m for m in entry["members"] if m["kind"] == "node" and m["status"] == "added"]
    assert any("y" in m["signature"] for m in added_node)


def test_build_sequence_change_list_messages() -> None:
    old = Project(
        source_language="python",
        sequences=[
            Sequence(
                name="flow",
                lifelines=[Lifeline(name="self")],
                messages=[Message(sender="self", receiver="self", label="old()")],
            )
        ],
    )
    new = Project(
        source_language="python",
        sequences=[
            Sequence(
                name="flow",
                lifelines=[Lifeline(name="self"), Lifeline(name="other")],
                messages=[Message(sender="self", receiver="other", label="new()")],
            )
        ],
    )
    annotated = diff_projects(old, new)
    out = build_sequence_change_list(annotated)
    assert len(out) == 1
    e = out[0]
    assert e["diagramKind"] == "sequence"
    msg_stats = sorted(m["status"] for m in e["members"] if m["kind"] == "message")
    assert msg_stats == ["added", "removed"]
    ll_added = [m for m in e["members"] if m["kind"] == "lifeline" and m["status"] == "added"]
    assert any(m["signature"] == "other" for m in ll_added)


def test_change_list_summarises_added_and_changed() -> None:
    old_base = Class(name="Animal", qualified_name="animals.Animal")
    new_base = Class(
        name="Animal",
        qualified_name="animals.Animal",
        attributes=[Attribute(name="legs", type="int")],
    )
    new_dog = Class(name="Dog", qualified_name="animals.Dog", bases=["Animal"])

    old = Project(
        source_language="python",
        packages=[Package(name="animals", qualified_name="animals", classes=[old_base])],
    )
    new = Project(
        source_language="python",
        packages=[
            Package(
                name="animals",
                qualified_name="animals",
                classes=[new_base, new_dog],
            )
        ],
    )
    annotated = diff_projects(old, new)
    changes = build_change_list(annotated)

    kinds = [c["kind"] for c in changes]
    # Changed comes before added per our ranking
    assert kinds == ["changed", "added"]
    animal = next(c for c in changes if c["classQname"] == "animals.Animal")
    assert "legs:int" in {m["signature"] for m in animal["members"]}


# ---------------- usage-derived edges & external bases ----------------

def _edge_pairs(graph) -> set[tuple[str, str, str]]:
    """(source_label, target_label, kind) for every edge, via node-id lookup."""
    label = {n["id"]: n["name"] for n in graph["nodes"]}
    return {
        (label[e["source"]], label[e["target"]], e["kind"]) for e in graph["edges"]
    }


def test_class_graph_edges_from_method_signature() -> None:
    """Param/return types that resolve to a project class produce association edges."""
    snap = Class(name="Snapshot", qualified_name="m.Snapshot")
    viewer = Class(
        name="Viewer",
        qualified_name="m.Viewer",
        operations=[
            Operation(
                name="capture",
                parameters=[Parameter(name="s", type="Snapshot")],
                return_type="Snapshot",
            )
        ],
    )
    proj = Project(
        source_language="csharp",
        packages=[Package(name="m", qualified_name="m", classes=[snap, viewer])],
    )
    graph = build_class_graph(proj)
    assert ("Viewer", "Snapshot", "association") in _edge_pairs(graph)


def test_class_graph_edges_from_body_dependency() -> None:
    """`Class.dependencies` entries that resolve to a project class produce edges."""
    util = Class(name="Utils", qualified_name="m.Utils")
    caller = Class(name="Caller", qualified_name="m.Caller", dependencies=["Utils"])
    proj = Project(
        source_language="csharp",
        packages=[Package(name="m", qualified_name="m", classes=[util, caller])],
    )
    graph = build_class_graph(proj)
    assert ("Caller", "Utils", "association") in _edge_pairs(graph)


def test_class_graph_no_edgeless_usage_only_class() -> None:
    """A class referenced only via a method signature is not left orphaned."""
    snap = Class(name="Snapshot", qualified_name="m.Snapshot")
    viewer = Class(
        name="Viewer",
        qualified_name="m.Viewer",
        operations=[Operation(name="capture", return_type="Snapshot")],
    )
    proj = Project(
        source_language="csharp",
        packages=[Package(name="m", qualified_name="m", classes=[snap, viewer])],
    )
    graph = build_class_graph(proj)
    connected: set[str] = set()
    for e in graph["edges"]:
        connected.add(e["source"])
        connected.add(e["target"])
    edgeless = {n["name"] for n in graph["nodes"] if n["id"] not in connected}
    assert "Snapshot" not in edgeless


def test_class_graph_external_base_node_and_edge() -> None:
    """A base not defined in the project gets one shared external node + edge."""
    a = Class(name="ViewA", qualified_name="m.ViewA", bases=["MonoBehaviour"])
    b = Class(name="ViewB", qualified_name="m.ViewB", bases=["MonoBehaviour"])
    proj = Project(
        source_language="csharp",
        packages=[Package(name="m", qualified_name="m", classes=[a, b])],
    )
    graph = build_class_graph(proj)
    externals = [n for n in graph["nodes"] if n.get("kind") == "external"]
    # One shared MonoBehaviour hub, not one per subclass.
    assert [n["name"] for n in externals] == ["MonoBehaviour"]
    pairs = _edge_pairs(graph)
    assert ("ViewA", "MonoBehaviour", "inheritance") in pairs
    assert ("ViewB", "MonoBehaviour", "inheritance") in pairs


def test_package_graph_tolerates_external_nodes() -> None:
    """External placeholder nodes must not break package-level aggregation."""
    a = Class(name="ViewA", qualified_name="m.ViewA", bases=["MonoBehaviour"])
    proj = Project(
        source_language="csharp",
        packages=[Package(name="m", qualified_name="m", classes=[a])],
    )
    # Should not raise (external node id has no owning package).
    pkg_graph = build_package_graph(proj)
    assert pkg_graph["nodes"]
