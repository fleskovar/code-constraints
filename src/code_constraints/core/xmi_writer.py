"""Serialise `Project` to XMI 2.1 (OMG standard) with a custom diff namespace.

XMI itself has no concept of "this element was added / removed in a diff";
we attach `cdec:status` and `cdec:changeKind` attributes in a private namespace
that conforming readers are free to ignore.
"""

from __future__ import annotations

from hashlib import sha1
from pathlib import Path

from lxml import etree

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
    Message,
    Operation,
    Package,
    Parameter,
    Project,
    RuleAnnotation,
    Sequence,
    Visibility,
)

NS = {
    "xmi": "http://www.omg.org/spec/XMI/20110701",
    "uml": "http://www.omg.org/spec/UML/20110701",
    "cdec": "http://code-constraints/ext/1",
}
XMI = f"{{{NS['xmi']}}}"
UML = f"{{{NS['uml']}}}"
CDEC = f"{{{NS['cdec']}}}"

XMI_VERSION = "2.1"


def write_project(project: Project, path: str | Path) -> Path:
    """Serialise `project` to `path` (XMI 2.1). Returns the path."""
    tree = build_tree(project)
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    tree.write(
        str(out),
        pretty_print=True,
        xml_declaration=True,
        encoding="UTF-8",
    )
    return out


def build_tree(project: Project) -> etree._ElementTree:
    root = etree.Element(f"{XMI}XMI", nsmap=NS)
    root.set(f"{XMI}version", XMI_VERSION)

    model = etree.SubElement(root, f"{UML}Model")
    model.set(f"{XMI}id", "model-root")
    model.set("name", "RootModel")
    _set_status_attr(model, DiffStatus.UNCHANGED)  # always emit so readers see it
    model.set(f"{CDEC}sourceLanguage", project.source_language)
    if project.root_path:
        model.set(f"{CDEC}rootPath", project.root_path)

    for pkg in project.packages:
        _write_package(model, pkg)

    for activity in project.activities:
        _write_activity(model, activity)

    for seq in project.sequences:
        _write_sequence(model, seq)

    for assoc in project.associations:
        _write_association(model, assoc)

    return etree.ElementTree(root)


def _write_association(parent: etree._Element, assoc: Association) -> None:
    el = etree.SubElement(parent, "packagedElement")
    el.set(f"{XMI}type", "uml:Association")
    if assoc.name:
        el.set("name", assoc.name)
    el.set(f"{CDEC}source", assoc.source)
    el.set(f"{CDEC}target", assoc.target)
    if assoc.source_multiplicity:
        el.set(f"{CDEC}sourceMultiplicity", assoc.source_multiplicity)
    if assoc.target_multiplicity:
        el.set(f"{CDEC}targetMultiplicity", assoc.target_multiplicity)
    if assoc.source_role:
        el.set(f"{CDEC}sourceRole", assoc.source_role)
    if assoc.target_role:
        el.set(f"{CDEC}targetRole", assoc.target_role)
    _set_status_attr(el, assoc.status)


# ---------- packages / classes ----------

def _write_package(parent: etree._Element, pkg: Package) -> None:
    el = etree.SubElement(parent, "packagedElement")
    el.set(f"{XMI}type", "uml:Package")
    el.set(f"{XMI}id", pkg.stable_id())
    el.set("name", pkg.name)
    el.set(f"{CDEC}qualifiedName", pkg.qualified_name)
    _set_status_attr(el, pkg.status)
    _set_layout_attrs(el, pkg.layout)
    _write_owned_comment(el, pkg.description, owner_key=f"Package|{pkg.qualified_name}")
    for cls in pkg.classes:
        _write_class(el, cls)
    for sub in pkg.sub_packages:
        _write_package(el, sub)


def _write_class(parent: etree._Element, cls: Class) -> None:
    el = etree.SubElement(parent, "packagedElement")
    el.set(f"{XMI}type", _class_xmi_type(cls.kind))
    el.set(f"{XMI}id", cls.stable_id())
    el.set("name", cls.name)
    el.set(f"{CDEC}qualifiedName", cls.qualified_name)
    el.set(f"{CDEC}kind", cls.kind)
    _set_status_attr(el, cls.status)
    _set_layout_attrs(el, cls.layout)
    if cls.kind == "abstract":
        el.set("isAbstract", "true")
    if cls.location is not None:
        el.set(f"{CDEC}file", cls.location.file)
        el.set(f"{CDEC}startLine", str(cls.location.start_line))
        el.set(f"{CDEC}endLine", str(cls.location.end_line))

    _write_owned_comment(el, cls.description, owner_key=f"Class|{cls.qualified_name}")
    _write_rules(el, cls.rules)

    for base in cls.bases:
        gen = etree.SubElement(el, "generalization")
        gen.set(f"{XMI}type", "uml:Generalization")
        gen.set(f"{CDEC}general", base)

    for dep in cls.dependencies:
        dep_el = etree.SubElement(el, f"{CDEC}dependency")
        dep_el.set("type", dep)

    for attr in cls.attributes:
        _write_attribute(el, attr, owner_qname=cls.qualified_name)
    for op in cls.operations:
        _write_operation(el, op, owner_qname=cls.qualified_name)


def _class_xmi_type(kind: str) -> str:
    if kind == "interface":
        return "uml:Interface"
    if kind == "enum":
        return "uml:Enumeration"
    return "uml:Class"


def _write_attribute(parent: etree._Element, attr: Attribute, *, owner_qname: str = "") -> None:
    el = etree.SubElement(parent, "ownedAttribute")
    el.set(f"{XMI}type", "uml:Property")
    el.set("name", attr.name)
    el.set("visibility", attr.visibility.value)
    el.set(f"{CDEC}type", attr.type)
    if attr.is_static:
        el.set("isStatic", "true")
    if attr.is_readonly:
        el.set("isReadOnly", "true")
    if attr.default is not None:
        el.set(f"{CDEC}default", attr.default)
    _set_status_attr(el, attr.status)
    _write_owned_comment(
        el, attr.description, owner_key=f"Attribute|{owner_qname}|{attr.signature()}"
    )


def _write_operation(parent: etree._Element, op: Operation, *, owner_qname: str = "") -> None:
    el = etree.SubElement(parent, "ownedOperation")
    el.set(f"{XMI}type", "uml:Operation")
    el.set("name", op.name)
    el.set("visibility", op.visibility.value)
    if op.is_static:
        el.set("isStatic", "true")
    if op.is_abstract:
        el.set("isAbstract", "true")
    _set_status_attr(el, op.status)
    _write_owned_comment(
        el, op.description, owner_key=f"Operation|{owner_qname}|{op.signature()}"
    )
    _write_rules(el, op.rules)
    for param in op.parameters:
        _write_parameter(el, param, direction="in")
    if op.return_type:
        _write_parameter(el, Parameter(name="return", type=op.return_type), direction="return")


def _write_parameter(parent: etree._Element, p: Parameter, *, direction: str) -> None:
    el = etree.SubElement(parent, "ownedParameter")
    el.set(f"{XMI}type", "uml:Parameter")
    el.set("name", p.name)
    el.set("direction", direction)
    el.set(f"{CDEC}type", p.type)
    if p.default is not None:
        el.set(f"{CDEC}default", p.default)


# ---------- activities ----------

def _write_activity(parent: etree._Element, act: Activity) -> None:
    el = etree.SubElement(parent, "packagedElement")
    el.set(f"{XMI}type", "uml:Activity")
    el.set(f"{XMI}id", act.stable_id())
    el.set("name", act.name)
    el.set(f"{CDEC}granularity", act.granularity)
    _set_status_attr(el, act.status)
    if act.location is not None:
        el.set(f"{CDEC}file", act.location.file)
        el.set(f"{CDEC}startLine", str(act.location.start_line))
        el.set(f"{CDEC}endLine", str(act.location.end_line))

    for node in act.nodes:
        _write_activity_node(el, node)
    for edge in act.edges:
        _write_activity_edge(el, edge)


_NODE_XMI_TYPE = {
    "initial": "uml:InitialNode",
    "final": "uml:ActivityFinalNode",
    "action": "uml:OpaqueAction",
    "decision": "uml:DecisionNode",
    "merge": "uml:MergeNode",
    "fork": "uml:ForkNode",
    "join": "uml:JoinNode",
}


def _write_activity_node(parent: etree._Element, node: ActivityNode) -> None:
    el = etree.SubElement(parent, "node")
    el.set(f"{XMI}type", _NODE_XMI_TYPE[node.kind])
    el.set(f"{XMI}id", node.id)
    if node.label:
        el.set("name", node.label)
    _set_status_attr(el, node.status)
    _set_layout_attrs(el, node.layout)


def _write_activity_edge(parent: etree._Element, edge: ActivityEdge) -> None:
    el = etree.SubElement(parent, "edge")
    el.set(f"{XMI}type", "uml:ControlFlow")
    el.set("source", edge.source)
    el.set("target", edge.target)
    if edge.guard:
        el.set(f"{CDEC}guard", edge.guard)
    _set_status_attr(el, edge.status)
    _set_edge_layout_attrs(el, edge.edge_layout)


# ---------- sequences ----------

def _write_sequence(parent: etree._Element, seq: Sequence) -> None:
    el = etree.SubElement(parent, "packagedElement")
    el.set(f"{XMI}type", "uml:Interaction")
    el.set(f"{XMI}id", seq.stable_id())
    el.set("name", seq.name)
    _set_status_attr(el, seq.status)
    if seq.location is not None:
        el.set(f"{CDEC}file", seq.location.file)
        el.set(f"{CDEC}startLine", str(seq.location.start_line))
        el.set(f"{CDEC}endLine", str(seq.location.end_line))

    for lifeline in seq.lifelines:
        ll = etree.SubElement(el, "lifeline")
        ll.set(f"{XMI}type", "uml:Lifeline")
        ll.set("name", lifeline.name)
        ll.set(f"{CDEC}represents", lifeline.represents)
        if lifeline.column_x is not None:
            ll.set(f"{CDEC}columnX", str(lifeline.column_x))
        _set_status_attr(ll, lifeline.status)

    for msg in seq.messages:
        m = etree.SubElement(el, "message")
        m.set(f"{XMI}type", "uml:Message")
        m.set("name", msg.label)
        m.set(f"{CDEC}sender", msg.sender)
        m.set(f"{CDEC}receiver", msg.receiver)
        if msg.is_return:
            m.set(f"{CDEC}isReturn", "true")
        if msg.guard:
            m.set(f"{CDEC}guard", msg.guard)
        _set_status_attr(m, msg.status)

    for frag in seq.fragments:
        f = etree.SubElement(el, "fragment")
        f.set(f"{XMI}type", "uml:CombinedFragment")
        f.set(f"{CDEC}kind", frag.kind)
        f.set("name", frag.label)
        f.set(f"{CDEC}startRow", str(frag.start_row))
        f.set(f"{CDEC}endRow", str(frag.end_row))
        _set_status_attr(f, frag.status)


# ---------- helpers ----------

def _write_owned_comment(parent: etree._Element, text: str | None, *, owner_key: str) -> None:
    """Emit a standards-compliant `<ownedComment xmi:type="uml:Comment">` child.

    `owner_key` is folded into a deterministic `xmi:id` so repeated emits of the
    same project produce byte-identical XMI.
    """
    if not text:
        return
    el = etree.SubElement(parent, "ownedComment")
    el.set(f"{XMI}type", "uml:Comment")
    el.set(f"{XMI}id", _comment_id(owner_key))
    body = etree.SubElement(el, "body")
    body.text = text


def _comment_id(owner_key: str) -> str:
    h = sha1(f"comment|{owner_key}".encode("utf-8")).hexdigest()[:16]
    return f"comment-{h}"


def _write_rules(parent: etree._Element, rules: list[RuleAnnotation]) -> None:
    """Emit one `<cdec:rule>` child per architectural-rule tag, preserving
    declaration order. Args/kwargs round-trip as `<cdec:arg>` / `<cdec:kwarg>`
    children so the source text survives verbatim."""
    for rule in rules:
        el = etree.SubElement(parent, f"{CDEC}rule")
        el.set("name", rule.name)
        for value in rule.args:
            arg = etree.SubElement(el, f"{CDEC}arg")
            arg.set("value", value)
        for key, value in rule.kwargs.items():
            kw = etree.SubElement(el, f"{CDEC}kwarg")
            kw.set("key", key)
            kw.set("value", value)


def _set_status_attr(el: etree._Element, status: DiffStatus) -> None:
    el.set(f"{CDEC}status", status.value)


def _set_layout_attrs(el: etree._Element, layout: Layout | None) -> None:
    if layout is None:
        return
    el.set(f"{CDEC}x", _fmt_num(layout.x))
    el.set(f"{CDEC}y", _fmt_num(layout.y))
    el.set(f"{CDEC}width", _fmt_num(layout.width))
    el.set(f"{CDEC}height", _fmt_num(layout.height))
    if layout.collapsed:
        el.set(f"{CDEC}collapsed", "true")


def _set_edge_layout_attrs(el: etree._Element, edge_layout: EdgeLayout | None) -> None:
    if edge_layout is None or not edge_layout.waypoints:
        return
    encoded = ";".join(f"{_fmt_num(x)},{_fmt_num(y)}" for x, y in edge_layout.waypoints)
    el.set(f"{CDEC}waypoints", encoded)


def _fmt_num(n: float) -> str:
    """Compact numeric format: integers stay integral, others go through repr."""
    if n == int(n):
        return str(int(n))
    return repr(n)
