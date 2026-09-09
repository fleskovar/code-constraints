"""Parse a Python project (directory of .py files) into a `code_constraints.core.Project`.

Strategy:
- Walk the directory; every `.py` file is parsed with `ast.parse`.
- Packages are derived from directory structure relative to the root.
- Each `ClassDef` becomes a `code_constraints.core.Class`. Methods become `Operation`s.
  Class-level type-annotated assignments and `self.x = ...` in `__init__`
  become `Attribute`s.
- Activity / sequence tags found in source are forwarded to `activity.py` and
  `sequence.py` (built later) which turn tagged regions into UML elements.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from code_constraints.core.model import (
    Attribute,
    Class,
    Operation,
    Package,
    Parameter,
    Project,
    SourceLocation,
    Visibility,
)
from code_constraints.core.tags import TagInstance, find_tags
from code_constraints.python.activity import build_activity_from_tag
from code_constraints.python.rules_extract import ImportMap, build_import_map, extract_rules
from code_constraints.python.sequence import build_sequence_from_tag


def parse_project(root: str | Path) -> Project:
    root_path = Path(root).resolve()
    if not root_path.is_dir():
        raise ValueError(f"not a directory: {root_path}")

    project = Project(source_language="python", root_path=str(root_path))
    package_index: dict[str, Package] = {}

    for py_file in sorted(root_path.rglob("*.py")):
        if _should_skip(py_file):
            continue
        _parse_file(py_file, root_path, project, package_index)

    return project


_SKIP_DIR_NAMES = {"__pycache__", ".venv", "venv", ".tox", "build", "dist", ".git"}


def _should_skip(p: Path) -> bool:
    return any(part in _SKIP_DIR_NAMES for part in p.parts)


def _parse_file(
    file: Path,
    root: Path,
    project: Project,
    package_index: dict[str, Package],
) -> None:
    rel = file.relative_to(root)
    package_qn = _qualified_package_name(rel)
    pkg = _ensure_package(project, package_qn, package_index)

    source = file.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(source, filename=str(file))
    except SyntaxError:
        return

    file_str = str(rel.as_posix())
    import_map = build_import_map(tree)

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            cls = _class_from_node(node, package_qn, file_str, import_map)
            pkg.classes.append(cls)

    tags = find_tags(source, comment_prefix="#")
    for tag in tags:
        if tag.kind == "uml-activity" and not tag.self_closed:
            act = build_activity_from_tag(tag, tree, source, file=file_str)
            if act is not None:
                project.activities.append(act)
        elif tag.kind == "uml-sequence" and not tag.self_closed:
            seq = build_sequence_from_tag(tag, tree, source, file=file_str)
            if seq is not None:
                project.sequences.append(seq)


def _qualified_package_name(rel_file: Path) -> str:
    parts = list(rel_file.parts[:-1])  # drop the file itself
    if not parts:
        return "__root__"
    return ".".join(parts)


def _ensure_package(
    project: Project, qualified_name: str, index: dict[str, Package]
) -> Package:
    if qualified_name in index:
        return index[qualified_name]

    if qualified_name == "__root__":
        pkg = Package(name="__root__", qualified_name="__root__")
        project.packages.append(pkg)
        index[qualified_name] = pkg
        return pkg

    parts = qualified_name.split(".")
    parent_qn = ".".join(parts[:-1]) if len(parts) > 1 else None
    if parent_qn is None:
        pkg = Package(name=parts[0], qualified_name=qualified_name)
        project.packages.append(pkg)
    else:
        parent = _ensure_package(project, parent_qn, index)
        pkg = Package(name=parts[-1], qualified_name=qualified_name)
        parent.sub_packages.append(pkg)
    index[qualified_name] = pkg
    return pkg


# ---------- class / member extraction ----------

def _class_from_node(
    node: ast.ClassDef, package_qn: str, file: str, import_map: ImportMap
) -> Class:
    qn = f"{package_qn}.{node.name}" if package_qn and package_qn != "__root__" else node.name
    cls = Class(
        name=node.name,
        qualified_name=qn,
        kind=_class_kind(node),
        bases=[_unparse(b) for b in node.bases],
        location=SourceLocation(
            file=file,
            start_line=getattr(node, "lineno", 0),
            end_line=getattr(node, "end_lineno", 0) or getattr(node, "lineno", 0),
        ),
        description=ast.get_docstring(node, clean=True) or None,
        rules=extract_rules(node.decorator_list, import_map),
    )

    for body_node in node.body:
        if isinstance(body_node, ast.AnnAssign) and isinstance(body_node.target, ast.Name):
            cls.attributes.append(
                Attribute(
                    name=body_node.target.id,
                    type=_unparse(body_node.annotation) if body_node.annotation else "",
                    visibility=_visibility(body_node.target.id),
                    is_static=True,
                    default=_unparse(body_node.value) if body_node.value else None,
                )
            )
        elif isinstance(body_node, ast.Assign):
            for tgt in body_node.targets:
                if isinstance(tgt, ast.Name):
                    cls.attributes.append(
                        Attribute(
                            name=tgt.id,
                            type="",
                            visibility=_visibility(tgt.id),
                            is_static=True,
                            default=_unparse(body_node.value) if body_node.value else None,
                        )
                    )
        elif isinstance(body_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            cls.operations.append(_operation_from_func(body_node, import_map))
            cls.dependencies.extend(_body_type_refs(body_node))
            if body_node.name == "__init__":
                for attr in _instance_attributes_from_init(body_node):
                    if not any(a.name == attr.name for a in cls.attributes):
                        cls.attributes.append(attr)

    cls.dependencies = _dedupe_refs(cls.dependencies, drop=node.name)
    return cls


def _class_kind(node: ast.ClassDef) -> str:
    for base in node.bases:
        base_name = _unparse(base)
        if base_name in {"ABC", "abc.ABC"}:
            return "abstract"
        if base_name in {"Enum", "IntEnum", "enum.Enum", "enum.IntEnum"}:
            return "enum"
        if base_name in {"Protocol", "typing.Protocol"}:
            return "interface"
    for kw in node.keywords:
        if kw.arg == "metaclass" and _unparse(kw.value) in {"ABCMeta", "abc.ABCMeta"}:
            return "abstract"
    return "class"


def _operation_from_func(
    node: ast.FunctionDef | ast.AsyncFunctionDef, import_map: ImportMap
) -> Operation:
    params: list[Parameter] = []
    args = node.args
    pos = list(args.posonlyargs) + list(args.args)
    defaults = list(args.defaults)
    default_offset = len(pos) - len(defaults)
    for i, arg in enumerate(pos):
        if arg.arg == "self":
            continue
        default = (
            _unparse(defaults[i - default_offset]) if i >= default_offset else None
        )
        params.append(
            Parameter(
                name=arg.arg,
                type=_unparse(arg.annotation) if arg.annotation else "",
                default=default,
            )
        )
    for arg, default in zip(args.kwonlyargs, args.kw_defaults):
        params.append(
            Parameter(
                name=arg.arg,
                type=_unparse(arg.annotation) if arg.annotation else "",
                default=_unparse(default) if default else None,
            )
        )

    is_static = any(_is_decorator(d, "staticmethod") for d in node.decorator_list)
    is_abstract = any(
        _is_decorator(d, "abstractmethod") or _is_decorator(d, "abc.abstractmethod")
        for d in node.decorator_list
    )

    return Operation(
        name=node.name,
        parameters=params,
        return_type=_unparse(node.returns) if node.returns else "",
        visibility=_visibility(node.name),
        is_static=is_static,
        is_abstract=is_abstract,
        description=ast.get_docstring(node, clean=True) or None,
        rules=extract_rules(node.decorator_list, import_map),
    )


def _instance_attributes_from_init(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[Attribute]:
    out: list[Attribute] = []
    for stmt in ast.walk(node):
        if isinstance(stmt, ast.AnnAssign) and _is_self_attr(stmt.target):
            assert isinstance(stmt.target, ast.Attribute)
            out.append(
                Attribute(
                    name=stmt.target.attr,
                    type=_unparse(stmt.annotation) if stmt.annotation else "",
                    visibility=_visibility(stmt.target.attr),
                )
            )
        elif isinstance(stmt, ast.Assign):
            for tgt in stmt.targets:
                if _is_self_attr(tgt):
                    assert isinstance(tgt, ast.Attribute)
                    out.append(
                        Attribute(
                            name=tgt.attr,
                            type="",
                            visibility=_visibility(tgt.attr),
                        )
                    )
    return out


def _is_self_attr(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "self"
    )


def _is_decorator(dec: ast.expr, name: str) -> bool:
    return _unparse(dec) == name


def _visibility(name: str) -> Visibility:
    if name.startswith("__") and not name.endswith("__"):
        return Visibility.PRIVATE
    if name.startswith("_"):
        return Visibility.PROTECTED
    return Visibility.PUBLIC


def _unparse(node: ast.AST | None) -> str:
    if node is None:
        return ""
    try:
        return ast.unparse(node)
    except Exception:
        return ""


_PASCAL_IDENT_RE = re.compile(r"^[A-Z][A-Za-z0-9_]*$")


def _body_type_refs(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    """Collect PascalCase names referenced inside a function body.

    Mirrors the C# parser heuristic: a PascalCase `Name` (a constructor call
    `Foo()`, a static-call receiver `Foo.bar()`, a local annotation, etc.) is a
    candidate type reference. `resolve_association` later keeps only those that
    map to a project class.
    """
    out: list[str] = []
    seen: set[str] = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Name) and n.id not in seen and _PASCAL_IDENT_RE.match(n.id):
            seen.add(n.id)
            out.append(n.id)
    return out


def _dedupe_refs(refs: list[str], *, drop: str = "") -> list[str]:
    """Order-preserving dedupe, dropping a given name (the owning class)."""
    out: list[str] = []
    seen: set[str] = set()
    for r in refs:
        if r == drop or r in seen:
            continue
        seen.add(r)
        out.append(r)
    return out
