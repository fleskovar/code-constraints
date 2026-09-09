"""Structural comparator for the architecture-reference gate (`cdec reference test`).

Decoupled from `code_constraints.core.diff` on purpose. `diff_projects` matches members by
`signature()` and only marks a matched member CHANGED when its *rule tags* differ,
so it is blind to visibility / static / abstract / readonly changes and to class
`kind` changes. The reference gate must reject all of those, so it walks both
`Project`s itself and reports every structural deviation as a `Deviation`.

Matching strategy (chosen so the human messages read as "changed", not
"removed + added"):
- classes      -> by qualified name
- attributes   -> by name within the class
- operations   -> by name within the class, with full-signature fallback for
                  overload groups (C# can declare several operations per name)
"""

from __future__ import annotations

from dataclasses import dataclass

from code_constraints.core.model import Attribute, Class, Operation, Project


@dataclass
class Deviation:
    """A single structural difference between the reference and current code.

    `category` is a stable machine id (e.g. "attribute-changed"); `member` is the
    attribute/operation signature when the deviation is member-level, else None.
    `old` / `new` carry the differing values for machine consumers (None for pure
    add/remove deviations).
    """

    category: str
    qualified_name: str
    message: str
    member: str | None = None
    old: str | None = None
    new: str | None = None

    def sort_key(self) -> tuple[str, str, str]:
        return (self.qualified_name, self.member or "", self.category)


def compare_to_reference(reference: Project, current: Project) -> list[Deviation]:
    """Return every structural deviation of `current` from `reference`.

    Raises ValueError when the two projects are in different source languages
    (matching `diff_projects`' guard), since a cross-language comparison is
    meaningless.
    """
    if reference.source_language != current.source_language:
        raise ValueError(
            f"cannot compare across languages: "
            f"{reference.source_language} -> {current.source_language}"
        )

    out: list[Deviation] = []
    ref_by_qn = {c.qualified_name: c for c in reference.iter_classes()}
    cur_by_qn = {c.qualified_name: c for c in current.iter_classes()}

    for qn, cur_cls in cur_by_qn.items():
        if qn not in ref_by_qn:
            out.append(
                Deviation(
                    category="class-added",
                    qualified_name=qn,
                    message=f"Class '{qn}' was added.",
                )
            )
        else:
            out.extend(_compare_class(ref_by_qn[qn], cur_cls))

    for qn in ref_by_qn:
        if qn not in cur_by_qn:
            out.append(
                Deviation(
                    category="class-removed",
                    qualified_name=qn,
                    message=f"Class '{qn}' was removed.",
                )
            )

    out.sort(key=Deviation.sort_key)
    return out


def _compare_class(ref: Class, cur: Class) -> list[Deviation]:
    out: list[Deviation] = []
    qn = cur.qualified_name

    if ref.kind != cur.kind:
        out.append(
            Deviation(
                category="class-kind-changed",
                qualified_name=qn,
                message=f"Class '{qn}' kind changed from {ref.kind} to {cur.kind}.",
                old=ref.kind,
                new=cur.kind,
            )
        )

    ref_bases, cur_bases = sorted(ref.bases), sorted(cur.bases)
    if ref_bases != cur_bases:
        out.append(
            Deviation(
                category="class-bases-changed",
                qualified_name=qn,
                message=(
                    f"Class '{qn}' base classes changed from "
                    f"[{', '.join(ref_bases)}] to [{', '.join(cur_bases)}]."
                ),
                old=", ".join(ref_bases),
                new=", ".join(cur_bases),
            )
        )

    out.extend(_compare_attributes(qn, ref.attributes, cur.attributes))
    out.extend(_compare_operations(qn, ref.operations, cur.operations))
    return out


# ---------- attributes ----------

def _compare_attributes(
    qn: str, ref: list[Attribute], cur: list[Attribute]
) -> list[Deviation]:
    out: list[Deviation] = []
    ref_by_name = {a.name: a for a in ref}
    cur_by_name = {a.name: a for a in cur}

    for name, a in cur_by_name.items():
        if name not in ref_by_name:
            out.append(
                Deviation(
                    category="attribute-added",
                    qualified_name=qn,
                    member=a.signature(),
                    message=f"Property '{a.signature()}' was added to '{qn}'.",
                )
            )
        else:
            out.extend(_compare_attribute_pair(qn, ref_by_name[name], a))

    for name, a in ref_by_name.items():
        if name not in cur_by_name:
            out.append(
                Deviation(
                    category="attribute-removed",
                    qualified_name=qn,
                    member=a.signature(),
                    message=f"Property '{a.signature()}' was removed from '{qn}'.",
                )
            )
    return out


def _compare_attribute_pair(qn: str, ref: Attribute, cur: Attribute) -> list[Deviation]:
    changes = _diff_fields(
        ref,
        cur,
        [
            ("type", "type"),
            ("visibility", "access level"),
            ("is_static", "static"),
            ("is_readonly", "readonly"),
            ("default", "default value"),
        ],
    )
    if not changes:
        return []
    summary = "; ".join(desc for desc, _, _ in changes)
    return [
        Deviation(
            category="attribute-changed",
            qualified_name=qn,
            member=cur.signature(),
            message=f"Property '{cur.name}' on '{qn}' changed: {summary}.",
            old="; ".join(f"{label}={old}" for label, old, _ in changes),
            new="; ".join(f"{label}={new}" for label, _, new in changes),
        )
    ]


# ---------- operations ----------

def _compare_operations(
    qn: str, ref: list[Operation], cur: list[Operation]
) -> list[Deviation]:
    out: list[Deviation] = []
    ref_by_name = _group_by_name(ref)
    cur_by_name = _group_by_name(cur)

    for name, cur_ops in cur_by_name.items():
        ref_ops = ref_by_name.get(name)
        if not ref_ops:
            for op in cur_ops:
                out.append(
                    Deviation(
                        category="operation-added",
                        qualified_name=qn,
                        member=op.signature(),
                        message=f"Method '{op.signature()}' was added to '{qn}'.",
                    )
                )
            continue
        if len(ref_ops) == 1 and len(cur_ops) == 1:
            out.extend(_compare_operation_pair(qn, ref_ops[0], cur_ops[0]))
        else:
            out.extend(_compare_operation_overloads(qn, ref_ops, cur_ops))

    for name, ref_ops in ref_by_name.items():
        if name not in cur_by_name:
            for op in ref_ops:
                out.append(
                    Deviation(
                        category="operation-removed",
                        qualified_name=qn,
                        member=op.signature(),
                        message=f"Method '{op.signature()}' was removed from '{qn}'.",
                    )
                )
    return out


def _compare_operation_overloads(
    qn: str, ref_ops: list[Operation], cur_ops: list[Operation]
) -> list[Deviation]:
    """Overload group (>1 op sharing a name): match on full signature so we can
    only report clean add/remove — a modifier-only change on one overload still
    surfaces because the signature is unchanged yet the pair compares equal here,
    so fall through to a per-signature modifier check."""
    out: list[Deviation] = []
    ref_by_sig = {o.signature(): o for o in ref_ops}
    cur_by_sig = {o.signature(): o for o in cur_ops}
    for sig, op in cur_by_sig.items():
        if sig not in ref_by_sig:
            out.append(
                Deviation(
                    category="operation-added",
                    qualified_name=qn,
                    member=sig,
                    message=f"Method '{sig}' was added to '{qn}'.",
                )
            )
        else:
            out.extend(_compare_operation_modifiers(qn, ref_by_sig[sig], op))
    for sig, op in ref_by_sig.items():
        if sig not in cur_by_sig:
            out.append(
                Deviation(
                    category="operation-removed",
                    qualified_name=qn,
                    member=sig,
                    message=f"Method '{sig}' was removed from '{qn}'.",
                )
            )
    return out


def _compare_operation_pair(qn: str, ref: Operation, cur: Operation) -> list[Deviation]:
    out: list[Deviation] = []
    ref_params = _params_repr(ref)
    cur_params = _params_repr(cur)
    if ref_params != cur_params:
        out.append(
            Deviation(
                category="operation-signature-changed",
                qualified_name=qn,
                member=cur.signature(),
                message=(
                    f"Method '{cur.name}' on '{qn}' signature changed from "
                    f"({ref_params}) to ({cur_params})."
                ),
                old=ref_params,
                new=cur_params,
            )
        )
    if ref.return_type != cur.return_type:
        out.append(
            Deviation(
                category="operation-return-type-changed",
                qualified_name=qn,
                member=cur.signature(),
                message=(
                    f"Method '{cur.name}' on '{qn}' return type changed from "
                    f"'{ref.return_type}' to '{cur.return_type}'."
                ),
                old=ref.return_type,
                new=cur.return_type,
            )
        )
    out.extend(_compare_operation_modifiers(qn, ref, cur))
    return out


def _compare_operation_modifiers(qn: str, ref: Operation, cur: Operation) -> list[Deviation]:
    changes = _diff_fields(
        ref,
        cur,
        [
            ("visibility", "access level"),
            ("is_static", "static"),
            ("is_abstract", "abstract"),
        ],
    )
    if not changes:
        return []
    summary = "; ".join(desc for desc, _, _ in changes)
    return [
        Deviation(
            category="operation-modifier-changed",
            qualified_name=qn,
            member=cur.signature(),
            message=f"Method '{cur.name}' on '{qn}' modifiers changed: {summary}.",
            old="; ".join(f"{label}={old}" for label, old, _ in changes),
            new="; ".join(f"{label}={new}" for label, _, new in changes),
        )
    ]


# ---------- shared helpers ----------

def _diff_fields(ref, cur, fields: list[tuple[str, str]]):
    """Return [(human_desc, old_str, new_str)] for each field that differs.

    `fields` is a list of (attr_name, label). Enum/None values are stringified.
    """
    changes = []
    for attr_name, label in fields:
        old_val = _scalar(getattr(ref, attr_name))
        new_val = _scalar(getattr(cur, attr_name))
        if old_val != new_val:
            changes.append((f"{label} {old_val} -> {new_val}", old_val, new_val))
    return changes


def _scalar(value) -> str:
    if value is None:
        return "none"
    # Visibility / other str-enums carry a readable .value.
    return str(getattr(value, "value", value))


def _params_repr(op: Operation) -> str:
    return ", ".join(
        f"{p.name}:{p.type}" + (f"={p.default}" if p.default is not None else "")
        for p in op.parameters
    )


def _group_by_name(ops: list[Operation]) -> dict[str, list[Operation]]:
    grouped: dict[str, list[Operation]] = {}
    for op in ops:
        grouped.setdefault(op.name, []).append(op)
    return grouped
