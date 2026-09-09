"""Build SvelteFlow-friendly JSON graph payloads from a `Project`.

The DOT emitter renders to a static SVG; this module renders to a dict that
the frontend hydrates into an interactive SvelteFlow canvas. The two share the
inheritance + association edge logic via `code_constraints.core.associations`.
"""

from __future__ import annotations

from typing import Any

from code_constraints.core.associations import resolve_association
from code_constraints.core.model import (
    Activity,
    Attribute,
    Class,
    DiffStatus,
    Operation,
    Package,
    Project,
    RuleAnnotation,
    Sequence,
)


# C# enum backing types (and the like) land in the base list (`enum X : byte`)
# but are not supertypes — don't render them as external base nodes.
_PRIMITIVE_BASE_NAMES = frozenset({
    "byte", "sbyte", "short", "ushort", "int", "uint", "long", "ulong",
    "char", "bool", "float", "double", "decimal", "string", "object",
})

_SEQUENCE_SAFE = str.maketrans({".": "_", "/": "_", " ": "_", "<": "_", ">": "_", "(": "_", ")": "_"})


def _seq_safe(name: str) -> str:
    return name.translate(_SEQUENCE_SAFE)


def build_class_graph(project: Project) -> dict[str, Any]:
    """Return {nodes, edges, meta} for a UML class diagram.

    Node and edge ids match `Class.stable_id()` so they survive re-parses and
    can drive cross-revision matching for the diff walkthrough.
    """
    # Dedupe by stable_id: two classes sharing a qualified name (C# partials,
    # accidentally duplicated module paths, etc.) would otherwise produce
    # duplicate SvelteFlow node ids and crash the canvas with each_key_duplicate.
    # Keep the first occurrence; later duplicates are silently dropped.
    seen_ids: set[str] = set()
    classes: list[Class] = []
    for c in project.iter_classes():
        if c.stable_id() in seen_ids:
            continue
        seen_ids.add(c.stable_id())
        classes.append(c)
    qname_to_id: dict[str, str] = {c.qualified_name: c.stable_id() for c in classes}
    short_counts: dict[str, int] = {}
    for c in classes:
        short_counts[c.name] = short_counts.get(c.name, 0) + 1
    short_to_id: dict[str, str] = {
        c.name: c.stable_id() for c in classes if short_counts[c.name] == 1
    }

    nodes: list[dict[str, Any]] = [_class_to_node(cls) for cls in classes]

    edges: list[dict[str, Any]] = []
    inheritance_pairs: set[tuple[str, str]] = set()

    # External supertypes (framework bases like MonoBehaviour, or interfaces not
    # defined in the project) get a single shared placeholder node each, so a
    # class that only inherits from outside the project still reads as connected
    # rather than orphaned.
    external_node_ids: set[str] = set()

    def _external_base_node(base: str) -> str:
        simple = base.split(".")[-1].split("<")[0].strip() or base
        nid = f"external::{simple}"
        if nid not in external_node_ids:
            external_node_ids.add(nid)
            nodes.append({
                "id": nid,
                "qualifiedName": simple,
                "name": simple,
                "kind": "external",
                "external": True,
                "package": "",
                "status": "unchanged",
                "description": None,
                "attributes": [],
                "operations": [],
                "rules": [],
                "location": None,
            })
        return nid

    # Inheritance: child → parent. Bases that resolve to a project class link to
    # that node; bases that don't (framework types, external interfaces) link to
    # a shared external placeholder node.
    for cls in classes:
        source_id = cls.stable_id()
        for base in cls.bases:
            target_id = qname_to_id.get(base) or short_to_id.get(base.split(".")[-1])
            if target_id is None:
                simple = base.split(".")[-1].split("<")[0].strip()
                if simple in _PRIMITIVE_BASE_NAMES:
                    continue
                target_id = _external_base_node(base)
            if target_id == source_id:
                continue
            pair = (source_id, target_id)
            if pair in inheritance_pairs:
                continue
            inheritance_pairs.add(pair)
            edges.append({
                "id": f"{source_id}--{target_id}--inheritance",
                "source": source_id,
                "target": target_id,
                "kind": "inheritance",
                "multiplicity": "",
                "status": cls.status.value,
                # The base reference lives on the source (child) class header —
                # recorded so the edge-focus popup can highlight where it comes from.
                "members": [{"kind": "inheritance", "signature": base}],
            })

    # Associations collapse to one edge per (source, target) pair, but several
    # members of the source class can contribute to the same edge (a field, a
    # method return/param, an explicit association). We keep one edge dict per
    # pair and accumulate every contributing member onto it, so the edge-focus
    # popup can highlight exactly which rows of the source class produce the
    # reference. Multiplicity/status keep the FIRST contributor's value.
    assoc_edge_by_pair: dict[tuple[str, str], dict[str, Any]] = {}

    def _record_assoc(
        source_id: str,
        target_id: str,
        multiplicity: str,
        status_val: str,
        member: dict[str, str] | None,
    ) -> None:
        if source_id == target_id:
            return
        pair = (source_id, target_id)
        # An inheritance edge already covers this pair — don't shadow it with an
        # association (matches the original dedup behaviour).
        if pair in inheritance_pairs:
            return
        edge = assoc_edge_by_pair.get(pair)
        if edge is None:
            edge = {
                "id": f"{source_id}--{target_id}--association",
                "source": source_id,
                "target": target_id,
                "kind": "association",
                "multiplicity": multiplicity,
                "status": status_val,
                "members": [],
            }
            assoc_edge_by_pair[pair] = edge
            edges.append(edge)
        if member is not None and member not in edge["members"]:
            edge["members"].append(member)

    # Field-derived associations (aggregation/composition).
    for cls in classes:
        source_id = cls.stable_id()
        for attr in cls.attributes:
            target_qn, multiplicity = resolve_association(attr.type, project)
            if target_qn is None:
                continue
            target_id = qname_to_id[target_qn]
            _record_assoc(
                source_id,
                target_id,
                multiplicity,
                attr.status.value,
                {"kind": "attribute", "signature": attr.signature()},
            )

    # Associations implied by *usage*: method parameter / return types and types
    # referenced inside method bodies (`cls.dependencies`). A class used only as
    # an argument, a return value, or via a static call still connects to the
    # types it depends on. Return/param uses pin to the owning operation row;
    # body-level dependencies can't be pinned to a member, so they add no member.
    def _add_usage_assoc(
        source_id: str,
        raw_type: str,
        status_val: str,
        member: dict[str, str] | None,
    ) -> None:
        target_qn, multiplicity = resolve_association(raw_type, project)
        if target_qn is None:
            return
        target_id = qname_to_id.get(target_qn)
        if target_id is None:
            return
        _record_assoc(source_id, target_id, multiplicity, status_val, member)

    for cls in classes:
        source_id = cls.stable_id()
        for op in cls.operations:
            op_member = {"kind": "operation", "signature": op.signature()}
            _add_usage_assoc(source_id, op.return_type, op.status.value, op_member)
            for param in op.parameters:
                _add_usage_assoc(source_id, param.type, op.status.value, op_member)
        for dep in cls.dependencies:
            _add_usage_assoc(source_id, dep, cls.status.value, None)

    # Explicit associations declared on the project (editor-authored). Dedup
    # against attribute-derived ones so a class that both has a typed field and
    # an explicit association doesn't double-render. If only the explicit form
    # exists, that's the one we emit. Editor-authored, so no source member row
    # to pin to.
    for assoc in project.associations:
        source_id = qname_to_id.get(assoc.source) or short_to_id.get(
            assoc.source.split(".")[-1]
        )
        target_id = qname_to_id.get(assoc.target) or short_to_id.get(
            assoc.target.split(".")[-1]
        )
        if source_id is None or target_id is None:
            continue
        multiplicity = assoc.target_multiplicity or assoc.source_multiplicity or ""
        _record_assoc(source_id, target_id, multiplicity, assoc.status.value, None)

    return {
        "nodes": nodes,
        "edges": edges,
        "meta": {
            "count": len(nodes),
            "sourceLanguage": project.source_language,
        },
    }


def _class_to_node(cls: Class) -> dict[str, Any]:
    package = cls.qualified_name.rsplit(".", 1)[0] if "." in cls.qualified_name else ""
    return {
        "id": cls.stable_id(),
        "qualifiedName": cls.qualified_name,
        "name": cls.name,
        "kind": cls.kind,
        "package": package,
        "status": cls.status.value,
        "description": cls.description,
        "attributes": [_attr(a) for a in cls.attributes],
        "operations": [_op(o) for o in cls.operations],
        "rules": [_rule(r) for r in cls.rules],
        "location": _location(cls),
    }


def _rule(r: RuleAnnotation) -> dict[str, Any]:
    return {"name": r.name, "args": list(r.args), "kwargs": dict(r.kwargs)}


def _attr(a: Attribute) -> dict[str, Any]:
    return {
        "name": a.name,
        "type": a.type,
        "visibility": a.visibility.value,
        "isStatic": a.is_static,
        "status": a.status.value,
        "signature": a.signature(),
        "description": a.description,
    }


def _op(o: Operation) -> dict[str, Any]:
    return {
        "name": o.name,
        "signature": o.signature(),
        "returnType": o.return_type,
        "visibility": o.visibility.value,
        "isStatic": o.is_static,
        "isAbstract": o.is_abstract,
        "status": o.status.value,
        "description": o.description,
        "rules": [_rule(r) for r in o.rules],
    }


def _location(cls: Class) -> dict[str, Any] | None:
    if cls.location is None:
        return None
    return {
        "file": cls.location.file,
        "startLine": cls.location.start_line,
        "endLine": cls.location.end_line,
    }


def build_package_graph(project: Project) -> dict[str, Any]:
    """Nodes and dependency edges for a UML package diagram.

    Emits one flat node per package. Dependency edges are derived by
    aggregating class-level inheritance + association edges to the package
    level: if any class in package A references any class in package B
    (A ≠ B), there's a `dependency` edge from A to B. Edges are deduped per
    (source, target) pair.

    Defensive: dedupes by `stable_id` so duplicate qualified names (e.g. C#
    partial classes) don't produce duplicate SvelteFlow node ids.
    """
    # Walk every package (recursively) for the flat node list.
    seen_ids: set[str] = set()
    pkg_nodes: list[dict[str, Any]] = []
    pkg_by_qname: dict[str, Package] = {}
    for pkg in _walk_pkgs(project.packages):
        if pkg.stable_id() in seen_ids:
            continue
        seen_ids.add(pkg.stable_id())
        pkg_by_qname[pkg.qualified_name] = pkg
        # Recursively count classes in self + sub-packages so the badge is meaningful.
        total_classes = sum(len(p.classes) for p in _walk_pkgs([pkg]))
        pkg_nodes.append({
            "id": pkg.stable_id(),
            "kind": "package",
            "name": pkg.name,
            "qualifiedName": pkg.qualified_name,
            "parentQname": (
                pkg.qualified_name.rsplit(".", 1)[0]
                if "." in pkg.qualified_name
                else ""
            ),
            "status": pkg.status.value,
            "description": pkg.description,
            "classCount": total_classes,
        })

    # Map class qualified_name → owning-package qualified_name.
    cls_to_pkg_qname: dict[str, str] = {}
    for pkg in _walk_pkgs(project.packages):
        for cls in pkg.classes:
            cls_to_pkg_qname[cls.qualified_name] = pkg.qualified_name

    pkg_id_by_qname: dict[str, str] = {
        n["qualifiedName"]: n["id"] for n in pkg_nodes
    }

    # Walk class graph once to derive package-level dependencies.
    class_graph = build_class_graph(project)
    # We need to map class-graph node ids → class qualified_name (already on the node).
    cls_id_to_qname: dict[str, str] = {
        n["id"]: n["qualifiedName"] for n in class_graph["nodes"]
    }

    seen_pairs: set[tuple[str, str]] = set()
    edges: list[dict[str, Any]] = []
    for e in class_graph["edges"]:
        src_cls = cls_id_to_qname.get(e["source"])
        tgt_cls = cls_id_to_qname.get(e["target"])
        if not src_cls or not tgt_cls:
            continue
        src_pkg_qname = cls_to_pkg_qname.get(src_cls)
        tgt_pkg_qname = cls_to_pkg_qname.get(tgt_cls)
        if not src_pkg_qname or not tgt_pkg_qname:
            continue
        if src_pkg_qname == tgt_pkg_qname:
            continue
        src_id = pkg_id_by_qname.get(src_pkg_qname)
        tgt_id = pkg_id_by_qname.get(tgt_pkg_qname)
        if not src_id or not tgt_id:
            continue
        key = (src_id, tgt_id)
        if key in seen_pairs:
            continue
        seen_pairs.add(key)
        # Propagate diff status pessimistically: if any underlying class-level
        # edge is non-unchanged, mark the dependency as changed.
        edges.append({
            "id": f"{src_id}--{tgt_id}",
            "source": src_id,
            "target": tgt_id,
            "kind": "dependency",
            "multiplicity": "",
            "status": e.get("status", "unchanged"),
        })

    return {
        "nodes": pkg_nodes,
        "edges": edges,
        "meta": {"count": len(pkg_nodes), "edgeCount": len(edges)},
    }


def _walk_pkgs(packages: list[Package]):
    for p in packages:
        yield p
        yield from _walk_pkgs(p.sub_packages)


def build_activity_graph(project: Project, name: str) -> dict[str, Any]:
    """Nodes + edges for one activity diagram, keyed by activity name."""
    act = next((a for a in project.activities if a.name == name), None)
    if act is None:
        raise KeyError(f"activity {name!r} not found")

    nodes = [
        {
            "id": n.id,
            "kind": n.kind,
            "label": n.label,
            "status": n.status.value,
        }
        for n in act.nodes
    ]
    edges = [
        {
            "id": f"{e.source}--{e.target}--{i}",
            "source": e.source,
            "target": e.target,
            "guard": e.guard,
            "status": e.status.value,
        }
        for i, e in enumerate(act.edges)
    ]
    return {
        "nodes": nodes,
        "edges": edges,
        "meta": {
            "count": len(nodes),
            "name": act.name,
            "granularity": act.granularity,
        },
    }


def build_change_list(project: Project) -> list[dict[str, Any]]:
    """Class-level change summary for diff walkthrough.

    Returns one entry per class whose status is not UNCHANGED. Each entry
    carries the class's stable_id (so the canvas can fitView onto it) and a
    bullet list of added / removed attribute & operation signatures so the
    UI can highlight exactly what differs.

    Empty for a non-diff XMI.
    """
    out: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for cls in project.iter_classes():
        if cls.status == DiffStatus.UNCHANGED:
            continue
        if cls.stable_id() in seen_ids:
            continue
        seen_ids.add(cls.stable_id())
        members: list[dict[str, Any]] = []
        added_a = 0
        removed_a = 0
        added_o = 0
        removed_o = 0
        for a in cls.attributes:
            if a.status == DiffStatus.ADDED:
                added_a += 1
                members.append({"kind": "attribute", "signature": a.signature(), "status": "added"})
            elif a.status == DiffStatus.REMOVED:
                removed_a += 1
                members.append({"kind": "attribute", "signature": a.signature(), "status": "removed"})
        for o in cls.operations:
            if o.status == DiffStatus.ADDED:
                added_o += 1
                members.append({"kind": "operation", "signature": o.signature(), "status": "added"})
            elif o.status == DiffStatus.REMOVED:
                removed_o += 1
                members.append({"kind": "operation", "signature": o.signature(), "status": "removed"})

        kind = (
            "added"
            if cls.status == DiffStatus.ADDED
            else "removed"
            if cls.status == DiffStatus.REMOVED
            else "changed"
        )
        bits = []
        if added_a: bits.append(f"+{added_a} attr{'s' if added_a != 1 else ''}")
        if removed_a: bits.append(f"-{removed_a} attr{'s' if removed_a != 1 else ''}")
        if added_o: bits.append(f"+{added_o} op{'s' if added_o != 1 else ''}")
        if removed_o: bits.append(f"-{removed_o} op{'s' if removed_o != 1 else ''}")
        summary = (
            f"{cls.name}: {kind}"
            if not bits
            else f"{cls.name}: {', '.join(bits)}"
        )

        out.append({
            "classId": cls.stable_id(),
            "classQname": cls.qualified_name,
            "kind": kind,
            "summary": summary,
            "members": members,
        })

    # Order: changed classes first (most interesting), then added, then removed,
    # alphabetised within each group by qualified name.
    rank = {"changed": 0, "added": 1, "removed": 2}
    out.sort(key=lambda e: (rank.get(e["kind"], 9), e["classQname"]))
    return out


def build_sequence_graph(project: Project, name: str) -> dict[str, Any]:
    """Lifeline / message graph for one sequence diagram.

    The frontend lays this out by `column` (lifeline index) and `row` (message
    index); this builder stays geometry-agnostic. Removed (ghost) lifelines
    are placed after surviving ones in declared order so their column index
    stays stable; removed messages keep their position in the diff'd `messages`
    list (which is already how `_diff_sequence` arranges them).
    """
    seq = next((s for s in project.sequences if s.name == name), None)
    if seq is None:
        raise KeyError(f"sequence {name!r} not found")

    lifelines: list[dict[str, Any]] = []
    lifeline_id_by_name: dict[str, str] = {}
    for col, ll in enumerate(seq.lifelines):
        lid = f"ll-{_seq_safe(ll.name)}"
        lifeline_id_by_name[ll.name] = lid
        lifelines.append({
            "id": lid,
            "name": ll.name,
            "represents": ll.represents,
            "column": col,
            "status": ll.status.value,
        })

    messages: list[dict[str, Any]] = []
    for row, m in enumerate(seq.messages):
        messages.append({
            "id": f"msg-{row}",
            "sender": lifeline_id_by_name.get(m.sender, f"ll-{_seq_safe(m.sender)}"),
            "receiver": lifeline_id_by_name.get(m.receiver, f"ll-{_seq_safe(m.receiver)}"),
            "label": m.label,
            "isReturn": m.is_return,
            "guard": m.guard,
            "row": row,
            "status": m.status.value,
        })

    fragments = [
        {
            "id": f"frag-{i}",
            "kind": f.kind,
            "label": f.label,
            "startRow": f.start_row,
            "endRow": f.end_row,
            "status": f.status.value,
        }
        for i, f in enumerate(seq.fragments)
    ]

    return {
        "lifelines": lifelines,
        "messages": messages,
        "fragments": fragments,
        "meta": {
            "name": seq.name,
            "lifelineCount": len(lifelines),
            "messageCount": len(messages),
            "fragmentCount": len(fragments),
        },
    }


def build_activity_change_list(project: Project) -> list[dict[str, Any]]:
    """Per-activity diff summary for the activity walkthrough.

    Returns one entry per activity whose status is not UNCHANGED, ordered
    changed → added → removed → alphabetised within group. Each entry lists
    added/removed node and edge signatures so the panel can render
    bullets and the canvas can fitView onto a specific node.
    """
    out: list[dict[str, Any]] = []
    for act in project.activities:
        if act.status == DiffStatus.UNCHANGED:
            continue
        added_n = removed_n = added_e = removed_e = 0
        members: list[dict[str, Any]] = []
        for n in act.nodes:
            if n.status == DiffStatus.ADDED:
                added_n += 1
                members.append({"kind": "node", "nodeId": n.id, "signature": f"{n.kind}: {n.label or '(unlabelled)'}", "status": "added"})
            elif n.status == DiffStatus.REMOVED:
                removed_n += 1
                members.append({"kind": "node", "nodeId": n.id, "signature": f"{n.kind}: {n.label or '(unlabelled)'}", "status": "removed"})
        for e in act.edges:
            if e.status == DiffStatus.ADDED:
                added_e += 1
                guard = f" [{e.guard}]" if e.guard else ""
                members.append({"kind": "edge", "signature": f"{e.source} → {e.target}{guard}", "status": "added"})
            elif e.status == DiffStatus.REMOVED:
                removed_e += 1
                guard = f" [{e.guard}]" if e.guard else ""
                members.append({"kind": "edge", "signature": f"{e.source} → {e.target}{guard}", "status": "removed"})

        kind = (
            "added" if act.status == DiffStatus.ADDED
            else "removed" if act.status == DiffStatus.REMOVED
            else "changed"
        )
        bits = []
        if added_n: bits.append(f"+{added_n} node{'s' if added_n != 1 else ''}")
        if removed_n: bits.append(f"-{removed_n} node{'s' if removed_n != 1 else ''}")
        if added_e: bits.append(f"+{added_e} edge{'s' if added_e != 1 else ''}")
        if removed_e: bits.append(f"-{removed_e} edge{'s' if removed_e != 1 else ''}")
        summary = f"{act.name}: {kind}" if not bits else f"{act.name}: {', '.join(bits)}"

        out.append({
            "diagramKind": "activity",
            "diagramName": act.name,
            "diagramId": act.stable_id(),
            "kind": kind,
            "summary": summary,
            "members": members,
        })

    rank = {"changed": 0, "added": 1, "removed": 2}
    out.sort(key=lambda e: (rank.get(e["kind"], 9), e["diagramName"]))
    return out


def build_sequence_change_list(project: Project) -> list[dict[str, Any]]:
    """Per-sequence diff summary mirroring the activity change-list shape."""
    out: list[dict[str, Any]] = []
    for seq in project.sequences:
        if seq.status == DiffStatus.UNCHANGED:
            continue
        added_ll = removed_ll = added_m = removed_m = 0
        members: list[dict[str, Any]] = []
        for ll in seq.lifelines:
            if ll.status == DiffStatus.ADDED:
                added_ll += 1
                members.append({"kind": "lifeline", "signature": ll.name, "status": "added"})
            elif ll.status == DiffStatus.REMOVED:
                removed_ll += 1
                members.append({"kind": "lifeline", "signature": ll.name, "status": "removed"})
        for i, m in enumerate(seq.messages):
            guard_prefix = f"[{m.guard}] " if m.guard else ""
            sig = f"{m.sender} → {m.receiver}: {guard_prefix}{m.label}"
            if m.status == DiffStatus.ADDED:
                added_m += 1
                members.append({"kind": "message", "messageRow": i, "signature": sig, "status": "added"})
            elif m.status == DiffStatus.REMOVED:
                removed_m += 1
                members.append({"kind": "message", "messageRow": i, "signature": sig, "status": "removed"})

        kind = (
            "added" if seq.status == DiffStatus.ADDED
            else "removed" if seq.status == DiffStatus.REMOVED
            else "changed"
        )
        bits = []
        if added_ll: bits.append(f"+{added_ll} lifeline{'s' if added_ll != 1 else ''}")
        if removed_ll: bits.append(f"-{removed_ll} lifeline{'s' if removed_ll != 1 else ''}")
        if added_m: bits.append(f"+{added_m} msg{'s' if added_m != 1 else ''}")
        if removed_m: bits.append(f"-{removed_m} msg{'s' if removed_m != 1 else ''}")
        summary = f"{seq.name}: {kind}" if not bits else f"{seq.name}: {', '.join(bits)}"

        out.append({
            "diagramKind": "sequence",
            "diagramName": seq.name,
            "diagramId": seq.stable_id(),
            "kind": kind,
            "summary": summary,
            "members": members,
        })

    rank = {"changed": 0, "added": 1, "removed": 2}
    out.sort(key=lambda e: (rank.get(e["kind"], 9), e["diagramName"]))
    return out


__all__ = [
    "build_class_graph",
    "build_package_graph",
    "build_activity_graph",
    "build_sequence_graph",
    "build_change_list",
    "build_activity_change_list",
    "build_sequence_change_list",
]
