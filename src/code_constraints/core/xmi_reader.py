"""Read XMI 2.1 files produced by `xmi_writer` back into a `Project`.

This reader is intentionally limited to documents we wrote ourselves; we do
not attempt to interpret arbitrary third-party XMI. The reader preserves the
diff annotations on the `cdec:` namespace.
"""

from __future__ import annotations

from pathlib import Path

from lxml import etree

from code_constraints.core.model import (
    Activity,
    ActivityEdge,
    ActivityNode,
    ActivityNodeKind,
    Association,
    Attribute,
    Class,
    DiffStatus,
    EdgeLayout,
    Fragment,
    Layout,
    Lifeline,
    Message,
    Operation,
    Package,
    Parameter,
    Project,
    RuleAnnotation,
    Sequence,
    SourceLocation,
    Visibility,
)
from code_constraints.core.xmi_writer import NS, UML, CDEC, XMI

_REVERSE_NODE_TYPE: dict[str, ActivityNodeKind] = {
    "uml:InitialNode": "initial",
    "uml:ActivityFinalNode": "final",
    "uml:OpaqueAction": "action",
    "uml:DecisionNode": "decision",
    "uml:MergeNode": "merge",
    "uml:ForkNode": "fork",
    "uml:JoinNode": "join",
}


def read_project(path: str | Path) -> Project:
    tree = etree.parse(str(path))
    root = tree.getroot()
    model = root.find(f"{UML}Model")
    if model is None:
        raise ValueError(f"{path}: no uml:Model element found")

    lang = model.get(f"{CDEC}sourceLanguage", "python")
    if lang not in (
        "python", "csharp", "typescript", "svelte", "odin", "lua", "julia",
    ):
        lang = "python"
    project = Project(
        source_language=lang,  # type: ignore[arg-type]
        root_path=model.get(f"{CDEC}rootPath", ""),
    )

    for child in model.findall("packagedElement"):
        xmi_type = child.get(f"{XMI}type")
        if xmi_type == "uml:Package":
            project.packages.append(_read_package(child))
        elif xmi_type == "uml:Activity":
            project.activities.append(_read_activity(child))
        elif xmi_type == "uml:Interaction":
            project.sequences.append(_read_sequence(child))
        elif xmi_type == "uml:Association":
            project.associations.append(_read_association(child))
        # Bare classes outside a package land in an implicit __root__ package
        elif xmi_type in ("uml:Class", "uml:Interface", "uml:Enumeration"):
            _ensure_root_package(project).classes.append(_read_class(child))

    return project


def _read_association(el: etree._Element) -> Association:
    return Association(
        source=el.get(f"{CDEC}source", ""),
        target=el.get(f"{CDEC}target", ""),
        name=el.get("name") or None,
        source_multiplicity=el.get(f"{CDEC}sourceMultiplicity") or None,
        target_multiplicity=el.get(f"{CDEC}targetMultiplicity") or None,
        source_role=el.get(f"{CDEC}sourceRole") or None,
        target_role=el.get(f"{CDEC}targetRole") or None,
        status=_read_status(el),
    )


def _ensure_root_package(project: Project) -> Package:
    for p in project.packages:
        if p.qualified_name == "__root__":
            return p
    pkg = Package(name="__root__", qualified_name="__root__")
    project.packages.append(pkg)
    return pkg


def _read_package(el: etree._Element) -> Package:
    pkg = Package(
        name=el.get("name", ""),
        qualified_name=el.get(f"{CDEC}qualifiedName", el.get("name", "")),
        status=_read_status(el),
        layout=_read_layout(el),
        description=_read_owned_comment(el),
    )
    for child in el.findall("packagedElement"):
        xmi_type = child.get(f"{XMI}type")
        if xmi_type == "uml:Package":
            pkg.sub_packages.append(_read_package(child))
        elif xmi_type in ("uml:Class", "uml:Interface", "uml:Enumeration"):
            pkg.classes.append(_read_class(child))
    return pkg


def _read_class(el: etree._Element) -> Class:
    cls = Class(
        name=el.get("name", ""),
        qualified_name=el.get(f"{CDEC}qualifiedName", el.get("name", "")),
        kind=el.get(f"{CDEC}kind", "class"),  # type: ignore[arg-type]
        status=_read_status(el),
        location=_read_location(el),
        layout=_read_layout(el),
        description=_read_owned_comment(el),
        rules=_read_rules(el),
    )
    for gen in el.findall("generalization"):
        base = gen.get(f"{CDEC}general", "")
        if base:
            cls.bases.append(base)
    for dep_el in el.findall(f"{CDEC}dependency"):
        dep = dep_el.get("type", "")
        if dep:
            cls.dependencies.append(dep)
    for attr_el in el.findall("ownedAttribute"):
        cls.attributes.append(_read_attribute(attr_el))
    for op_el in el.findall("ownedOperation"):
        cls.operations.append(_read_operation(op_el))
    return cls


def _read_attribute(el: etree._Element) -> Attribute:
    return Attribute(
        name=el.get("name", ""),
        type=el.get(f"{CDEC}type", ""),
        visibility=_read_visibility(el.get("visibility", "public")),
        is_static=el.get("isStatic") == "true",
        is_readonly=el.get("isReadOnly") == "true",
        default=el.get(f"{CDEC}default"),
        description=_read_owned_comment(el),
        status=_read_status(el),
    )


def _read_operation(el: etree._Element) -> Operation:
    params: list[Parameter] = []
    return_type = ""
    for p_el in el.findall("ownedParameter"):
        direction = p_el.get("direction", "in")
        if direction == "return":
            return_type = p_el.get(f"{CDEC}type", "")
        else:
            params.append(
                Parameter(
                    name=p_el.get("name", ""),
                    type=p_el.get(f"{CDEC}type", ""),
                    default=p_el.get(f"{CDEC}default"),
                )
            )
    return Operation(
        name=el.get("name", ""),
        parameters=params,
        return_type=return_type,
        visibility=_read_visibility(el.get("visibility", "public")),
        is_static=el.get("isStatic") == "true",
        is_abstract=el.get("isAbstract") == "true",
        description=_read_owned_comment(el),
        rules=_read_rules(el),
        status=_read_status(el),
    )


def _read_rules(el: etree._Element) -> list[RuleAnnotation]:
    rules: list[RuleAnnotation] = []
    for rule_el in el.findall(f"{CDEC}rule"):
        name = rule_el.get("name", "")
        if not name:
            continue
        args = [a.get("value", "") for a in rule_el.findall(f"{CDEC}arg")]
        kwargs = {
            kw.get("key", ""): kw.get("value", "")
            for kw in rule_el.findall(f"{CDEC}kwarg")
            if kw.get("key")
        }
        rules.append(RuleAnnotation(name=name, args=args, kwargs=kwargs))
    return rules


def _read_activity(el: etree._Element) -> Activity:
    act = Activity(
        name=el.get("name", ""),
        granularity=el.get(f"{CDEC}granularity", "control-flow"),  # type: ignore[arg-type]
        status=_read_status(el),
        location=_read_location(el),
    )
    for node_el in el.findall("node"):
        kind = _REVERSE_NODE_TYPE.get(node_el.get(f"{XMI}type", ""), "action")
        act.nodes.append(
            ActivityNode(
                id=node_el.get(f"{XMI}id", ""),
                kind=kind,
                label=node_el.get("name", ""),
                status=_read_status(node_el),
                layout=_read_layout(node_el),
            )
        )
    for edge_el in el.findall("edge"):
        act.edges.append(
            ActivityEdge(
                source=edge_el.get("source", ""),
                target=edge_el.get("target", ""),
                guard=edge_el.get(f"{CDEC}guard", ""),
                status=_read_status(edge_el),
                edge_layout=_read_edge_layout(edge_el),
            )
        )
    return act


def _read_sequence(el: etree._Element) -> Sequence:
    seq = Sequence(
        name=el.get("name", ""),
        status=_read_status(el),
        location=_read_location(el),
    )
    for ll_el in el.findall("lifeline"):
        col = ll_el.get(f"{CDEC}columnX")
        seq.lifelines.append(
            Lifeline(
                name=ll_el.get("name", ""),
                represents=ll_el.get(f"{CDEC}represents", ""),
                column_x=float(col) if col is not None else None,
                status=_read_status(ll_el),
            )
        )
    for m_el in el.findall("message"):
        seq.messages.append(
            Message(
                sender=m_el.get(f"{CDEC}sender", ""),
                receiver=m_el.get(f"{CDEC}receiver", ""),
                label=m_el.get("name", ""),
                is_return=m_el.get(f"{CDEC}isReturn") == "true",
                guard=m_el.get(f"{CDEC}guard", ""),
                status=_read_status(m_el),
            )
        )
    for f_el in el.findall("fragment"):
        try:
            start_row = int(f_el.get(f"{CDEC}startRow", "0"))
            end_row = int(f_el.get(f"{CDEC}endRow", "0"))
        except ValueError:
            continue
        kind_raw = f_el.get(f"{CDEC}kind", "alt")
        if kind_raw not in ("alt", "opt", "loop"):
            kind_raw = "alt"
        seq.fragments.append(
            Fragment(
                kind=kind_raw,  # type: ignore[arg-type]
                label=f_el.get("name", ""),
                start_row=start_row,
                end_row=end_row,
                status=_read_status(f_el),
            )
        )
    return seq


def _read_owned_comment(el: etree._Element) -> str | None:
    """Return the body text of the first `ownedComment` child, if any.

    Tolerant of multiple comments (takes the first) and of an absent
    `<body>` element (returns None).
    """
    comment = el.find("ownedComment")
    if comment is None:
        return None
    body = comment.find("body")
    if body is None or body.text is None:
        return None
    text = body.text.strip()
    return text or None


def _read_status(el: etree._Element) -> DiffStatus:
    raw = el.get(f"{CDEC}status", "unchanged")
    try:
        return DiffStatus(raw)
    except ValueError:
        return DiffStatus.UNCHANGED


def _read_visibility(raw: str) -> Visibility:
    try:
        return Visibility(raw)
    except ValueError:
        return Visibility.PUBLIC


def _read_location(el: etree._Element) -> SourceLocation | None:
    file = el.get(f"{CDEC}file")
    if not file:
        return None
    try:
        start = int(el.get(f"{CDEC}startLine", "0"))
        end = int(el.get(f"{CDEC}endLine", "0"))
    except ValueError:
        return None
    return SourceLocation(file=file, start_line=start, end_line=end)


def _read_layout(el: etree._Element) -> Layout | None:
    x = el.get(f"{CDEC}x")
    y = el.get(f"{CDEC}y")
    if x is None and y is None:
        return None
    try:
        return Layout(
            x=float(x or "0"),
            y=float(y or "0"),
            width=float(el.get(f"{CDEC}width", "0")),
            height=float(el.get(f"{CDEC}height", "0")),
            collapsed=el.get(f"{CDEC}collapsed") == "true",
        )
    except ValueError:
        return None


def _read_edge_layout(el: etree._Element) -> EdgeLayout | None:
    raw = el.get(f"{CDEC}waypoints")
    if not raw:
        return None
    waypoints: list[tuple[float, float]] = []
    for pair in raw.split(";"):
        if not pair:
            continue
        try:
            xs, ys = pair.split(",", 1)
            waypoints.append((float(xs), float(ys)))
        except ValueError:
            continue
    return EdgeLayout(waypoints=waypoints) if waypoints else None
