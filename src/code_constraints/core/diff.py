"""Diff two `Project` snapshots and produce a single annotated `Project`.

Matching is by stable identity:
- Packages and classes match on qualified name.
- Attributes / operations match on (name, type/signature) within the same class.
- Activities and sequences match on name.

Removed elements are *kept* in the output so renderers can show strikethrough.
"""

from __future__ import annotations

from copy import deepcopy

from code_constraints.core.model import (
    Activity,
    ActivityEdge,
    ActivityNode,
    Attribute,
    Class,
    DiffStatus,
    Operation,
    Package,
    Project,
    Sequence,
)


def diff_projects(old: Project, new: Project) -> Project:
    """Return an annotated `Project` based on `new`, with removed elements
    grafted in from `old` and `status` populated on every element.
    """
    if old.source_language != new.source_language:
        raise ValueError(
            f"cannot diff across languages: {old.source_language} -> {new.source_language}"
        )

    result = Project(source_language=new.source_language, root_path=new.root_path)
    result.packages = _diff_package_lists(old.packages, new.packages)
    result.activities = _diff_named_list(old.activities, new.activities, _diff_activity)
    result.sequences = _diff_named_list(old.sequences, new.sequences, _diff_sequence)
    return result


# ---------- packages ----------

def _diff_package_lists(
    old: list[Package], new: list[Package]
) -> list[Package]:
    old_by_qn = {p.qualified_name: p for p in old}
    new_by_qn = {p.qualified_name: p for p in new}
    out: list[Package] = []

    for qn, new_pkg in new_by_qn.items():
        if qn in old_by_qn:
            out.append(_diff_package(old_by_qn[qn], new_pkg))
        else:
            out.append(_mark_subtree(new_pkg, DiffStatus.ADDED))

    for qn, old_pkg in old_by_qn.items():
        if qn not in new_by_qn:
            out.append(_mark_subtree(old_pkg, DiffStatus.REMOVED))

    return out


def _diff_package(old: Package, new: Package) -> Package:
    merged = Package(name=new.name, qualified_name=new.qualified_name)
    merged.classes = _diff_class_lists(old.classes, new.classes)
    merged.sub_packages = _diff_package_lists(old.sub_packages, new.sub_packages)
    merged.status = (
        DiffStatus.CHANGED
        if any(c.status != DiffStatus.UNCHANGED for c in merged.classes)
        or any(p.status != DiffStatus.UNCHANGED for p in merged.sub_packages)
        else DiffStatus.UNCHANGED
    )
    return merged


def _mark_subtree(pkg: Package, status: DiffStatus) -> Package:
    pkg = deepcopy(pkg)
    pkg.status = status
    for cls in pkg.classes:
        cls.status = status
        for a in cls.attributes:
            a.status = status
        for o in cls.operations:
            o.status = status
    for sub in pkg.sub_packages:
        _mark_subtree(sub, status)
    return pkg


# ---------- classes ----------

def _diff_class_lists(old: list[Class], new: list[Class]) -> list[Class]:
    old_by_qn = {c.qualified_name: c for c in old}
    new_by_qn = {c.qualified_name: c for c in new}
    out: list[Class] = []

    for qn, new_cls in new_by_qn.items():
        if qn in old_by_qn:
            out.append(_diff_class(old_by_qn[qn], new_cls))
        else:
            out.append(_mark_class(new_cls, DiffStatus.ADDED))

    for qn, old_cls in old_by_qn.items():
        if qn not in new_by_qn:
            out.append(_mark_class(old_cls, DiffStatus.REMOVED))

    return out


def _diff_class(old: Class, new: Class) -> Class:
    merged = deepcopy(new)
    merged.attributes = _diff_members(old.attributes, new.attributes)
    merged.operations = _diff_members(old.operations, new.operations)

    any_changed = any(a.status != DiffStatus.UNCHANGED for a in merged.attributes) or any(
        o.status != DiffStatus.UNCHANGED for o in merged.operations
    )
    bases_changed = sorted(old.bases) != sorted(new.bases)
    rules_changed = old.rules != new.rules
    merged.status = (
        DiffStatus.CHANGED
        if any_changed or bases_changed or rules_changed
        else DiffStatus.UNCHANGED
    )
    return merged


def _mark_class(cls: Class, status: DiffStatus) -> Class:
    cls = deepcopy(cls)
    cls.status = status
    for a in cls.attributes:
        a.status = status
    for o in cls.operations:
        o.status = status
    return cls


def _diff_members(old_members, new_members):
    """Generic member differ for attributes and operations.

    Match by signature so a renamed-but-same-signature member counts as the
    same; a same-name-different-type attribute reports as changed (i.e. shows
    up once as removed-old and once as added-new — we keep this explicit
    rather than guessing rename semantics).
    """
    old_by_sig = {m.signature(): m for m in old_members}
    new_by_sig = {m.signature(): m for m in new_members}
    out = []

    for sig, new_m in new_by_sig.items():
        if sig in old_by_sig:
            m = deepcopy(new_m)
            old_rules = getattr(old_by_sig[sig], "rules", [])
            new_rules = getattr(new_m, "rules", [])
            m.status = (
                DiffStatus.CHANGED if old_rules != new_rules else DiffStatus.UNCHANGED
            )
            out.append(m)
        else:
            m = deepcopy(new_m)
            m.status = DiffStatus.ADDED
            out.append(m)

    for sig, old_m in old_by_sig.items():
        if sig not in new_by_sig:
            m = deepcopy(old_m)
            m.status = DiffStatus.REMOVED
            out.append(m)

    return out


# ---------- activities / sequences ----------

def _diff_named_list(old_list, new_list, diff_one):
    old_by_name = {x.name: x for x in old_list}
    new_by_name = {x.name: x for x in new_list}
    out = []
    for name, new_item in new_by_name.items():
        if name in old_by_name:
            out.append(diff_one(old_by_name[name], new_item))
        else:
            item = deepcopy(new_item)
            item.status = DiffStatus.ADDED
            out.append(item)
    for name, old_item in old_by_name.items():
        if name not in new_by_name:
            item = deepcopy(old_item)
            item.status = DiffStatus.REMOVED
            out.append(item)
    return out


def _diff_activity(old: Activity, new: Activity) -> Activity:
    """Per-node + per-edge diff. Nodes match on (kind, label); edges match on
    (source_kind, source_label, target_kind, target_label, guard) so renames of
    auto-generated node ids don't ghost every edge. Removed nodes/edges are
    appended to merged with status=REMOVED. The activity is CHANGED iff any
    child element is non-UNCHANGED.
    """
    merged = deepcopy(new)

    old_nodes_by_key: dict[tuple[str, str], ActivityNode] = {}
    for n in old.nodes:
        old_nodes_by_key.setdefault((n.kind, n.label), n)
    merged_nodes_by_key: dict[tuple[str, str], ActivityNode] = {}
    for n in merged.nodes:
        merged_nodes_by_key.setdefault((n.kind, n.label), n)

    for n in merged.nodes:
        key = (n.kind, n.label)
        n.status = DiffStatus.UNCHANGED if key in old_nodes_by_key else DiffStatus.ADDED

    for n in old.nodes:
        key = (n.kind, n.label)
        if key not in merged_nodes_by_key:
            ghost = deepcopy(n)
            ghost.status = DiffStatus.REMOVED
            merged.nodes.append(ghost)

    old_node_by_id = {n.id: n for n in old.nodes}
    merged_node_by_id = {n.id: n for n in merged.nodes}

    def edge_key(e: ActivityEdge, node_index: dict[str, ActivityNode]) -> tuple:
        src = node_index.get(e.source)
        tgt = node_index.get(e.target)
        sk = (src.kind, src.label) if src else (None, e.source)
        tk = (tgt.kind, tgt.label) if tgt else (None, e.target)
        return (sk, tk, e.guard)

    old_edge_keys = {edge_key(e, old_node_by_id) for e in old.edges}
    new_edge_keys = {edge_key(e, merged_node_by_id) for e in merged.edges}

    for e in merged.edges:
        k = edge_key(e, merged_node_by_id)
        e.status = DiffStatus.UNCHANGED if k in old_edge_keys else DiffStatus.ADDED

    for e in old.edges:
        if edge_key(e, old_node_by_id) not in new_edge_keys:
            ghost = deepcopy(e)
            ghost.status = DiffStatus.REMOVED
            merged.edges.append(ghost)

    any_changed = any(n.status != DiffStatus.UNCHANGED for n in merged.nodes) or any(
        e.status != DiffStatus.UNCHANGED for e in merged.edges
    )
    merged.status = DiffStatus.CHANGED if any_changed else DiffStatus.UNCHANGED
    return merged


def _diff_sequence(old: Sequence, new: Sequence) -> Sequence:
    merged = deepcopy(new)

    def _msg_key(m):
        # Include guard + is_return so changing only the surrounding
        # condition or swapping a call for a return is correctly diffed.
        return (m.sender, m.receiver, m.label, m.guard, m.is_return)

    def _frag_key(f):
        return (f.kind, f.label, f.start_row, f.end_row)

    new_msgs = {_msg_key(m) for m in new.messages}
    old_msgs = {_msg_key(m) for m in old.messages}
    new_lls = {ll.name for ll in new.lifelines}
    old_lls = {ll.name for ll in old.lifelines}
    new_frags = {_frag_key(f) for f in new.fragments}
    old_frags = {_frag_key(f) for f in old.fragments}

    for m in merged.messages:
        m.status = DiffStatus.UNCHANGED if _msg_key(m) in old_msgs else DiffStatus.ADDED
    for key in old_msgs - new_msgs:
        old_m = next(m for m in old.messages if _msg_key(m) == key)
        ghost = deepcopy(old_m)
        ghost.status = DiffStatus.REMOVED
        merged.messages.append(ghost)

    for ll in merged.lifelines:
        ll.status = DiffStatus.UNCHANGED if ll.name in old_lls else DiffStatus.ADDED
    for ll_name in old_lls - new_lls:
        old_ll = next(l for l in old.lifelines if l.name == ll_name)
        ghost_ll = deepcopy(old_ll)
        ghost_ll.status = DiffStatus.REMOVED
        merged.lifelines.append(ghost_ll)

    for f in merged.fragments:
        f.status = DiffStatus.UNCHANGED if _frag_key(f) in old_frags else DiffStatus.ADDED
    for key in old_frags - new_frags:
        old_f = next(f for f in old.fragments if _frag_key(f) == key)
        ghost_f = deepcopy(old_f)
        ghost_f.status = DiffStatus.REMOVED
        merged.fragments.append(ghost_f)

    merged.status = (
        DiffStatus.CHANGED
        if (new_msgs != old_msgs or new_lls != old_lls or new_frags != old_frags)
        else DiffStatus.UNCHANGED
    )
    return merged
