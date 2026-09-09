"""JSON <-> Project conversion for the editor bridge endpoints.

The editor in the browser holds a draft `Project` shaped like the Python
dataclasses; these helpers move it across the wire without growing a separate
schema. Field names are snake_case on both sides so the converters stay dumb.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from code_constraints.core.model import (
    Activity,
    ActivityEdge,
    ActivityNode,
    Association,
    Attribute,
    Class,
    DiffStatus,
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


def project_to_json(project: Project) -> dict[str, Any]:
    """Serialise a Project to a JSON-safe dict (enums become their .value)."""
    return _coerce(asdict(project))


def _coerce(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _coerce(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_coerce(v) for v in obj]
    if isinstance(obj, tuple):
        return [_coerce(v) for v in obj]
    if isinstance(obj, DiffStatus) or isinstance(obj, Visibility):
        return obj.value
    return obj


def project_from_json(data: dict[str, Any]) -> Project:
    """Reconstruct a Project from the JSON dict shape produced by `project_to_json`.

    Missing optional fields fall back to dataclass defaults. Unknown languages
    default to 'python' to keep the editor permissive.
    """
    lang = data.get("source_language", "python")
    if lang not in (
        "python", "csharp", "typescript", "svelte", "odin", "lua", "julia",
    ):
        lang = "python"
    project = Project(
        source_language=lang,  # type: ignore[arg-type]
        root_path=data.get("root_path", "") or "",
    )
    project.packages = [_read_package(p) for p in data.get("packages", []) or []]
    project.activities = [_read_activity(a) for a in data.get("activities", []) or []]
    project.sequences = [_read_sequence(s) for s in data.get("sequences", []) or []]
    project.associations = [_read_association(a) for a in data.get("associations", []) or []]
    return project


def _status(raw: Any) -> DiffStatus:
    try:
        return DiffStatus(raw) if raw else DiffStatus.UNCHANGED
    except ValueError:
        return DiffStatus.UNCHANGED


def _visibility(raw: Any) -> Visibility:
    try:
        return Visibility(raw) if raw else Visibility.PUBLIC
    except ValueError:
        return Visibility.PUBLIC


def _layout(raw: Any) -> Layout | None:
    if not raw:
        return None
    return Layout(
        x=float(raw.get("x", 0)),
        y=float(raw.get("y", 0)),
        width=float(raw.get("width", 0)),
        height=float(raw.get("height", 0)),
        collapsed=bool(raw.get("collapsed", False)),
    )


def _location(raw: Any) -> SourceLocation | None:
    if not raw:
        return None
    return SourceLocation(
        file=raw.get("file", ""),
        start_line=int(raw.get("start_line", 0)),
        end_line=int(raw.get("end_line", 0)),
    )


def _read_rules(raw: Any) -> list[RuleAnnotation]:
    out: list[RuleAnnotation] = []
    for r in raw or []:
        if not isinstance(r, dict) or not r.get("name"):
            continue
        out.append(
            RuleAnnotation(
                name=str(r["name"]),
                args=[str(a) for a in r.get("args", []) or []],
                kwargs={str(k): str(v) for k, v in (r.get("kwargs", {}) or {}).items()},
            )
        )
    return out


def _read_package(raw: dict[str, Any]) -> Package:
    return Package(
        name=raw.get("name", ""),
        qualified_name=raw.get("qualified_name", raw.get("name", "")),
        classes=[_read_class(c) for c in raw.get("classes", []) or []],
        sub_packages=[_read_package(p) for p in raw.get("sub_packages", []) or []],
        layout=_layout(raw.get("layout")),
        description=raw.get("description") or None,
        status=_status(raw.get("status")),
    )


def _read_class(raw: dict[str, Any]) -> Class:
    kind = raw.get("kind", "class")
    if kind not in ("class", "interface", "abstract", "enum", "struct", "record", "static"):
        kind = "class"
    return Class(
        name=raw.get("name", ""),
        qualified_name=raw.get("qualified_name", raw.get("name", "")),
        kind=kind,  # type: ignore[arg-type]
        attributes=[_read_attribute(a) for a in raw.get("attributes", []) or []],
        operations=[_read_operation(o) for o in raw.get("operations", []) or []],
        bases=list(raw.get("bases", []) or []),
        dependencies=list(raw.get("dependencies", []) or []),
        location=_location(raw.get("location")),
        layout=_layout(raw.get("layout")),
        description=raw.get("description") or None,
        rules=_read_rules(raw.get("rules")),
        status=_status(raw.get("status")),
    )


def _read_attribute(raw: dict[str, Any]) -> Attribute:
    return Attribute(
        name=raw.get("name", ""),
        type=raw.get("type", ""),
        visibility=_visibility(raw.get("visibility")),
        is_static=bool(raw.get("is_static", False)),
        is_readonly=bool(raw.get("is_readonly", False)),
        default=raw.get("default"),
        description=raw.get("description") or None,
        status=_status(raw.get("status")),
    )


def _read_operation(raw: dict[str, Any]) -> Operation:
    return Operation(
        name=raw.get("name", ""),
        parameters=[_read_parameter(p) for p in raw.get("parameters", []) or []],
        return_type=raw.get("return_type", ""),
        visibility=_visibility(raw.get("visibility")),
        is_static=bool(raw.get("is_static", False)),
        is_abstract=bool(raw.get("is_abstract", False)),
        description=raw.get("description") or None,
        rules=_read_rules(raw.get("rules")),
        status=_status(raw.get("status")),
    )


def _read_parameter(raw: dict[str, Any]) -> Parameter:
    return Parameter(
        name=raw.get("name", ""),
        type=raw.get("type", ""),
        default=raw.get("default"),
    )


def _read_association(raw: dict[str, Any]) -> Association:
    return Association(
        source=raw.get("source", ""),
        target=raw.get("target", ""),
        name=raw.get("name") or None,
        source_multiplicity=raw.get("source_multiplicity") or None,
        target_multiplicity=raw.get("target_multiplicity") or None,
        source_role=raw.get("source_role") or None,
        target_role=raw.get("target_role") or None,
        status=_status(raw.get("status")),
    )


def _read_activity(raw: dict[str, Any]) -> Activity:
    gran = raw.get("granularity", "control-flow")
    if gran not in ("control-flow", "statement", "calls"):
        gran = "control-flow"
    return Activity(
        name=raw.get("name", ""),
        nodes=[_read_activity_node(n) for n in raw.get("nodes", []) or []],
        edges=[_read_activity_edge(e) for e in raw.get("edges", []) or []],
        location=_location(raw.get("location")),
        granularity=gran,  # type: ignore[arg-type]
        status=_status(raw.get("status")),
    )


def _read_activity_node(raw: dict[str, Any]) -> ActivityNode:
    kind = raw.get("kind", "action")
    if kind not in ("initial", "final", "action", "decision", "merge", "fork", "join"):
        kind = "action"
    return ActivityNode(
        id=raw.get("id", ""),
        kind=kind,  # type: ignore[arg-type]
        label=raw.get("label", ""),
        layout=_layout(raw.get("layout")),
        status=_status(raw.get("status")),
    )


def _read_activity_edge(raw: dict[str, Any]) -> ActivityEdge:
    return ActivityEdge(
        source=raw.get("source", ""),
        target=raw.get("target", ""),
        guard=raw.get("guard", ""),
        status=_status(raw.get("status")),
    )


def _read_sequence(raw: dict[str, Any]) -> Sequence:
    return Sequence(
        name=raw.get("name", ""),
        lifelines=[
            Lifeline(
                name=l.get("name", ""),
                represents=l.get("represents", ""),
                column_x=l.get("column_x"),
                status=_status(l.get("status")),
            )
            for l in raw.get("lifelines", []) or []
        ],
        messages=[
            Message(
                sender=m.get("sender", ""),
                receiver=m.get("receiver", ""),
                label=m.get("label", ""),
                is_return=bool(m.get("is_return", False)),
                guard=m.get("guard", ""),
                status=_status(m.get("status")),
            )
            for m in raw.get("messages", []) or []
        ],
        fragments=[
            Fragment(
                kind=f.get("kind", "alt"),
                label=f.get("label", ""),
                start_row=int(f.get("start_row", 0)),
                end_row=int(f.get("end_row", 0)),
                status=_status(f.get("status")),
            )
            for f in raw.get("fragments", []) or []
        ],
        location=_location(raw.get("location")),
        status=_status(raw.get("status")),
    )


__all__ = ["project_to_json", "project_from_json"]
