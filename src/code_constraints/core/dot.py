"""Emit Graphviz DOT text from a `Project` (which may carry diff annotations).

DOT is the rendering intermediate; XMI is the on-disk source of truth.

Diff styling uses Graphviz's HTML-like labels:
- `BGCOLOR` on the table / row for added / removed / changed
- `<FONT COLOR="...">` for added (green) vs removed (red) text
- `<S>...</S>` strikethrough on removed members

The four diagram types render with different graph shapes:
- class:    record-style HTML tables, inheritance edges with `arrowhead=empty`
- package:  nested `subgraph cluster_*`
- activity: shape-keyed nodes (circle / box / diamond / doublecircle)
- sequence: header row + invisible step grid + dashed lifelines + message edges
"""

from __future__ import annotations

from code_constraints.core.associations import resolve_association
from code_constraints.core.model import (
    Activity,
    Attribute,
    Class,
    ClassKind,
    DiffStatus,
    Operation,
    Package,
    Project,
    Sequence,
    Visibility,
)

# colour palette (kept consistent with diff documentation)
COLOR_ADDED = "#DAF7DC"
COLOR_REMOVED = "#FBD7D7"
COLOR_CHANGED = "#FFF6CC"
TEXT_ADDED = "darkgreen"
TEXT_REMOVED = "red"

_VIS_SYMBOL = {
    Visibility.PUBLIC: "+",
    Visibility.PROTECTED: "#",
    Visibility.PRIVATE: "-",
    Visibility.PACKAGE: "~",
}


def _bgcolor_for(status: DiffStatus) -> str:
    """Returns a BGCOLOR attribute fragment (with leading space) or empty."""
    return {
        DiffStatus.ADDED: f' BGCOLOR="{COLOR_ADDED}"',
        DiffStatus.REMOVED: f' BGCOLOR="{COLOR_REMOVED}"',
        DiffStatus.CHANGED: f' BGCOLOR="{COLOR_CHANGED}"',
    }.get(status, "")


def _wrap_member_html(html_text: str, status: DiffStatus) -> str:
    if status == DiffStatus.ADDED:
        return f'<FONT COLOR="{TEXT_ADDED}">{html_text}</FONT>'
    if status == DiffStatus.REMOVED:
        return f'<FONT COLOR="{TEXT_REMOVED}"><S>{html_text}</S></FONT>'
    return html_text


def _esc(text: str) -> str:
    """HTML-escape for DOT HTML-labels."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _safe(name: str) -> str:
    """DOT identifier-safe form for a qualified name."""
    out: list[str] = []
    for ch in name:
        if ch.isalnum() or ch == "_":
            out.append(ch)
        else:
            out.append("_")
    return "".join(out) or "anon"


# ---------- class diagram ----------

def emit_class_diagram(project: Project) -> str:
    lines: list[str] = [
        'digraph "class" {',
        '  rankdir=BT;',
        '  graph [splines=ortho, nodesep=0.6, ranksep=0.8];',
        '  node [shape=none, fontname="Helvetica", fontsize=11];',
        '  edge [fontname="Helvetica", fontsize=10];',
    ]

    class_index: dict[str, str] = {}
    # qualified-name lookup is always unambiguous; short-name lookup only
    # works when the short name is unique across the project.
    short_name_counts: dict[str, int] = {}
    for cls in project.iter_classes():
        class_index[cls.qualified_name] = _safe(cls.qualified_name)
        short_name_counts[cls.name] = short_name_counts.get(cls.name, 0) + 1
    for cls in project.iter_classes():
        if short_name_counts[cls.name] == 1:
            class_index[cls.name] = _safe(cls.qualified_name)

    for cls in project.iter_classes():
        lines.append(_render_class_node(cls))

    # Inheritance edges (UML generalization: empty-triangle arrowhead, child -> parent).
    inheritance_pairs: set[tuple[str, str]] = set()
    for cls in project.iter_classes():
        for base in cls.bases:
            target = class_index.get(base)
            if target is None:
                target_id = f"ext_{_safe(base)}"
                lines.append(
                    f'  "{target_id}" [shape=box, style="dashed,rounded", label="{_esc(base)}"];'
                )
                target = target_id
            source = _safe(cls.qualified_name)
            lines.append(f'  "{source}" -> "{target}" [arrowhead=empty];')
            inheritance_pairs.add((source, target))

    # Association edges from class-typed attributes (UML aggregation/composition).
    # A typed field whose type resolves to another class in the project becomes
    # a directed association with a multiplicity label at the receiver end.
    seen_assoc: set[tuple[str, str]] = set()
    for cls in project.iter_classes():
        source = _safe(cls.qualified_name)
        for attr in cls.attributes:
            target_qn, multiplicity = resolve_association(attr.type, project)
            if target_qn is None:
                continue
            target = _safe(target_qn)
            if source == target:
                continue  # skip self-loops (e.g. linked-list-style next pointers)
            if (source, target) in inheritance_pairs:
                continue  # an inheritance edge already covers this pair
            if (source, target) in seen_assoc:
                continue  # one association edge per pair
            seen_assoc.add((source, target))
            head = f', headlabel="{multiplicity}"' if multiplicity else ""
            lines.append(
                f'  "{source}" -> "{target}" '
                f'[arrowhead=vee, style=solid{head}];'
            )

    lines.append("}")
    return "\n".join(lines)


def _render_class_node(cls: Class) -> str:
    kind_tag = _kind_tag(cls.kind)
    header = f"{kind_tag}<B>{_esc(cls.name)}</B>" if kind_tag else f"<B>{_esc(cls.name)}</B>"
    header_bg = _bgcolor_for(cls.status) or ' BGCOLOR="#f0f0f0"'

    rows: list[str] = [f'<TR><TD{header_bg}>{header}</TD></TR>']
    if cls.attributes:
        for attr in cls.attributes:
            rows.append(_render_attribute_row(attr))
    if cls.attributes and cls.operations:
        rows.append('<TR><TD BGCOLOR="#dddddd" HEIGHT="1"></TD></TR>')
    for op in cls.operations:
        rows.append(_render_operation_row(op))

    table = (
        '<TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0" CELLPADDING="4">'
        + "".join(rows)
        + "</TABLE>"
    )
    return f'  "{_safe(cls.qualified_name)}" [label=<{table}>];'


def _kind_tag(kind: ClassKind) -> str:
    if kind == "interface":
        return "&laquo;interface&raquo;<BR/>"
    if kind == "enum":
        return "&laquo;enumeration&raquo;<BR/>"
    if kind == "abstract":
        return "&laquo;abstract&raquo;<BR/>"
    if kind == "static":
        return "&laquo;static&raquo;<BR/>"
    return ""


def _render_attribute_row(attr: Attribute) -> str:
    sym = _VIS_SYMBOL.get(attr.visibility, "+")
    text = f"{sym} {_esc(attr.name)}"
    if attr.type:
        text += f" : {_esc(attr.type)}"
    if attr.is_static:
        text = f"<I>{text}</I>"
    inner = _wrap_member_html(text, attr.status)
    bg = _bgcolor_for(attr.status)
    return f'<TR><TD ALIGN="LEFT"{bg}>{inner}</TD></TR>'


def _render_operation_row(op: Operation) -> str:
    sym = _VIS_SYMBOL.get(op.visibility, "+")
    params = ", ".join(
        f"{_esc(p.name)}: {_esc(p.type)}" if p.type else _esc(p.name)
        for p in op.parameters
    )
    text = f"{sym} {_esc(op.name)}({params})"
    if op.return_type:
        text += f" : {_esc(op.return_type)}"
    if op.is_static:
        text = f"<I>{text}</I>"
    if op.is_abstract:
        text = f"<I>{text}</I>"
    inner = _wrap_member_html(text, op.status)
    bg = _bgcolor_for(op.status)
    return f'<TR><TD ALIGN="LEFT"{bg}>{inner}</TD></TR>'


# ---------- package diagram ----------

def emit_package_diagram(project: Project) -> str:
    lines: list[str] = [
        'digraph "package" {',
        '  compound=true;',
        '  graph [fontname="Helvetica", fontsize=11];',
        '  node [shape=box, style=rounded, fontname="Helvetica", fontsize=10];',
    ]
    for pkg in project.packages:
        _emit_package_cluster(pkg, lines, indent="  ")
    lines.append("}")
    return "\n".join(lines)


def _emit_package_cluster(pkg: Package, lines: list[str], *, indent: str) -> None:
    cluster_id = f"cluster_{_safe(pkg.qualified_name)}"
    fillcolor = (
        COLOR_ADDED
        if pkg.status == DiffStatus.ADDED
        else COLOR_REMOVED
        if pkg.status == DiffStatus.REMOVED
        else COLOR_CHANGED
        if pkg.status == DiffStatus.CHANGED
        else "#f5f5f5"
    )
    lines.append(f"{indent}subgraph {cluster_id} {{")
    lines.append(f'{indent}  label="{_esc(pkg.qualified_name)}";')
    lines.append(f'{indent}  style="filled,rounded";')
    lines.append(f'{indent}  fillcolor="{fillcolor}";')
    for cls in pkg.classes:
        node_bg = _bg_attr_for_status(cls.status)
        lines.append(
            f'{indent}  "{_safe(cls.qualified_name)}" '
            f'[label="{_esc(cls.name)}"{node_bg}];'
        )
    for sub in pkg.sub_packages:
        _emit_package_cluster(sub, lines, indent=indent + "  ")
    lines.append(f"{indent}}}")


def _bg_attr_for_status(status: DiffStatus) -> str:
    if status == DiffStatus.ADDED:
        return f', style="filled,rounded", fillcolor="{COLOR_ADDED}"'
    if status == DiffStatus.REMOVED:
        return f', style="filled,rounded", fillcolor="{COLOR_REMOVED}"'
    if status == DiffStatus.CHANGED:
        return f', style="filled,rounded", fillcolor="{COLOR_CHANGED}"'
    return ""


# ---------- activity diagram ----------

_ACTIVITY_SHAPE = {
    "initial": 'shape=circle, style=filled, fillcolor=black, width=0.3, label=""',
    "final": 'shape=doublecircle, style=filled, fillcolor=black, width=0.3, label=""',
    "action": 'shape=box, style="rounded,filled", fillcolor=white',
    "decision": 'shape=diamond, style=filled, fillcolor=white',
    "merge": 'shape=diamond, style=filled, fillcolor=white, label=""',
    "fork": 'shape=box, style=filled, fillcolor=black, height=0.05, label=""',
    "join": 'shape=box, style=filled, fillcolor=black, height=0.05, label=""',
}


def emit_activity_diagram(activity: Activity) -> str:
    lines: list[str] = [
        'digraph "activity" {',
        '  rankdir=TB;',
        '  graph [splines=true, nodesep=0.4, ranksep=0.5];',
        '  node [fontname="Helvetica", fontsize=10];',
        '  edge [fontname="Helvetica", fontsize=9];',
    ]
    for node in activity.nodes:
        base = _ACTIVITY_SHAPE.get(node.kind, _ACTIVITY_SHAPE["action"])
        # action/decision nodes get the label override; circles keep label=""
        if node.kind in ("action", "decision") and node.label:
            label = _diff_label(node.label, node.status)
            # Override the existing label= portion if present, else append.
            if "label=" in base:
                base = ", ".join(
                    p for p in base.split(", ") if not p.strip().startswith("label=")
                )
            attrs = f"{base}, label=<{label}>"
        else:
            attrs = base
        fill_override = _activity_fill_override(node.status)
        if fill_override:
            attrs += f", {fill_override}"
        lines.append(f'  "{node.id}" [{attrs}];')

    for edge in activity.edges:
        guard = ""
        if edge.guard:
            guard = f' [label="{_esc(edge.guard)}"]'
        elif edge.status == DiffStatus.ADDED:
            guard = f' [color="{TEXT_ADDED}"]'
        elif edge.status == DiffStatus.REMOVED:
            guard = f' [color="{TEXT_REMOVED}", style=dashed]'
        lines.append(f'  "{edge.source}" -> "{edge.target}"{guard};')

    lines.append("}")
    return "\n".join(lines)


def _diff_label(text: str, status: DiffStatus) -> str:
    return _wrap_member_html(_esc(text), status)


def _activity_fill_override(status: DiffStatus) -> str:
    if status == DiffStatus.ADDED:
        return f'fillcolor="{COLOR_ADDED}"'
    if status == DiffStatus.REMOVED:
        return f'fillcolor="{COLOR_REMOVED}"'
    if status == DiffStatus.CHANGED:
        return f'fillcolor="{COLOR_CHANGED}"'
    return ""


# ---------- sequence diagram ----------

def emit_sequence_diagram(seq: Sequence) -> str:
    """Best-effort UML sequence layout in Graphviz.

    Layout: a top header row of participants, then one row per message with
    invisible "step" nodes. Vertical dashed edges link a participant's steps to
    form its lifeline; each message is a labelled horizontal edge between the
    sender's and receiver's step nodes on the same row.
    """
    lines: list[str] = [
        'digraph "sequence" {',
        '  rankdir=TB;',
        '  graph [nodesep=0.6, ranksep=0.4];',
        '  node [fontname="Helvetica", fontsize=10];',
        '  edge [fontname="Helvetica", fontsize=9];',
    ]

    if not seq.lifelines:
        lines.append("}")
        return "\n".join(lines)

    lifeline_ids = [(ll, _safe(ll.name)) for ll in seq.lifelines]

    # Header row
    lines.append("  { rank=same;")
    for ll, lid in lifeline_ids:
        bg = _bg_attr_for_status(ll.status)
        lines.append(
            f'    "{lid}_head" [shape=box, style="filled,rounded", '
            f'fillcolor="#eef2ff"{bg}, label="{_esc(ll.name)}"];'
        )
    lines.append("  }")

    # Step nodes and message edges per row
    prev_step_per_lifeline: dict[str, str] = {lid: f"{lid}_head" for _, lid in lifeline_ids}
    for i, msg in enumerate(seq.messages, start=1):
        # Each lifeline gets an invisible step node on this row.
        row_node_ids: dict[str, str] = {}
        lines.append("  { rank=same;")
        for _, lid in lifeline_ids:
            step_id = f"{lid}_s{i}"
            row_node_ids[lid] = step_id
            lines.append(f'    "{step_id}" [shape=point, width=0.01, label=""];')
        lines.append("  }")
        # Connect each lifeline's previous step to its step on this row (dashed).
        for _, lid in lifeline_ids:
            lines.append(
                f'  "{prev_step_per_lifeline[lid]}" -> "{row_node_ids[lid]}" '
                f'[style=dashed, arrowhead=none];'
            )
            prev_step_per_lifeline[lid] = row_node_ids[lid]
        # The message itself.
        sender_id = _safe(msg.sender)
        receiver_id = _safe(msg.receiver)
        src = row_node_ids.get(sender_id, row_node_ids[lifeline_ids[0][1]])
        dst = row_node_ids.get(receiver_id, row_node_ids[lifeline_ids[0][1]])
        arrow = "vee" if not msg.is_return else "open"
        style = "dashed" if msg.is_return else "solid"
        color = ""
        if msg.status == DiffStatus.ADDED:
            color = f', color="{TEXT_ADDED}", fontcolor="{TEXT_ADDED}"'
        elif msg.status == DiffStatus.REMOVED:
            color = f', color="{TEXT_REMOVED}", fontcolor="{TEXT_REMOVED}"'
        text = f"[{msg.guard}] {msg.label}" if msg.guard else msg.label
        label = _diff_label(text, msg.status)
        lines.append(
            f'  "{src}" -> "{dst}" [label=<{label}>, '
            f'arrowhead={arrow}, style={style}, constraint=false{color}];'
        )

    lines.append("}")
    return "\n".join(lines)
