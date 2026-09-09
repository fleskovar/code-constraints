"""Parse a Lua project (directory of .lua files) into a `code_constraints.core.Project`.

Uses `tree_sitter` with the `tree_sitter_lua` grammar. Syntactic only — Lua is
dynamically typed, so attribute and parameter types are left empty and
association edges come from capitalised identifiers used in bodies.

Lua has no classes, so the parser recognises the standard table-plus-metatable
idiom. Within one file, a local or global table becomes a `Class` when it shows
at least one of:

* a method or function declared on it (`function T:m()` / `function T.m()`),
* the `T.__index = T` self-index that marks a prototype,
* a metatable base (`setmetatable({}, { __index = Base })` → `bases: [Base]`),
* a `---@cdec` tag written above its declaration.

That last condition matters: it means tagging a table is enough to pull it into
the model even before it has methods. A plain `local cfg = {}` data table with
none of the four is *not* promoted, which keeps the diagram free of every
scratch local in the file.

Two consequences of Lua's dynamism worth knowing:

1. **Class tables are file-scoped.** A module is a file, so the walk resolves
   `function T:m()` against tables declared in the same file only — no
   cross-file guessing.
2. **Instance attributes come from every method, not just a constructor.** Lua
   has no `__init__` equivalent to privilege, so any `self.x = ...` in any
   method of `T` contributes the attribute `x`. This is broader than the Python
   parser's `__init__`-only rule, and deliberately so.

Free functions (`local function helper()`) have no receiver table, so they land
on a synthetic `static` class named after the file stem — the same UML
utility-class treatment the Odin parser gives package-scope procedures.
"""

from __future__ import annotations

from pathlib import Path

import tree_sitter_lua
from tree_sitter import Language, Node, Parser

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
from code_constraints.core.rules import SHIM_FILENAMES
from code_constraints.lua.rules_extract import extract_rules, rules_for_statements

_LANG = Language(tree_sitter_lua.language())
_PARSER = Parser(_LANG)

_SKIP_DIR_NAMES = {".git", "node_modules", "build", "out", ".luarocks", ".cdec_cache"}

# Metafields that describe the table rather than being data on it.
_METAFIELDS = frozenset(
    {
        "__index", "__newindex", "__call", "__tostring", "__eq", "__lt", "__le",
        "__add", "__sub", "__mul", "__div", "__mod", "__pow", "__unm", "__len",
        "__concat", "__gc", "__close", "__mode", "__name", "__metatable",
    }
)


def parse_project(root: str | Path) -> Project:
    root_path = Path(root).resolve()
    if not root_path.is_dir():
        raise ValueError(f"not a directory: {root_path}")

    project = Project(source_language="lua", root_path=str(root_path))
    package_index: dict[str, Package] = {}

    for lua_file in sorted(root_path.rglob("*.lua")):
        if _should_skip(lua_file):
            continue
        _parse_file(lua_file, root_path, project, package_index)

    return project


def _should_skip(p: Path) -> bool:
    if p.name in SHIM_FILENAMES:
        return True
    return any(part in _SKIP_DIR_NAMES for part in p.parts)


class _Candidate:
    """A table that might turn out to be a class, accumulated over one file."""

    __slots__ = (
        "name", "decl_nodes", "base", "self_indexed", "operations",
        "static_attrs", "instance_attrs", "deps", "line",
    )

    def __init__(self, name: str, line: int):
        self.name = name
        self.decl_nodes: list[Node] = []
        self.base: str = ""
        self.self_indexed = False
        self.operations: list[Operation] = []
        self.static_attrs: list[Attribute] = []
        self.instance_attrs: list[str] = []
        self.deps: list[str] = []
        self.line = line


def _parse_file(
    file: Path,
    root: Path,
    project: Project,
    package_index: dict[str, Package],
) -> None:
    source = file.read_bytes()
    tree = _PARSER.parse(source)
    rel = file.relative_to(root)
    file_str = rel.as_posix()
    package_qn = _qualified_package_name(rel)
    _ensure_package(project, package_qn, package_index)

    candidates: dict[str, _Candidate] = {}
    free_functions: list[Operation] = []
    free_deps: list[str] = []

    for stmt in tree.root_node.named_children:
        if stmt.type == "variable_declaration":
            _visit_assignment(_inner_assignment(stmt), stmt, source, candidates)
        elif stmt.type == "assignment_statement":
            _visit_assignment(stmt, stmt, source, candidates)
        elif stmt.type == "function_declaration":
            _visit_function(stmt, source, candidates, free_functions, free_deps)
        elif stmt.type == "function_call":
            _visit_setmetatable_call(stmt, source, candidates)

    pkg = _ensure_package(project, package_qn, package_index)
    for cand in candidates.values():
        cls = _to_class(cand, package_qn, source, file_str)
        if cls is not None:
            pkg.classes.append(cls)

    if free_functions:
        pkg.classes.append(
            _module_class(rel.stem, package_qn, file_str, free_functions, free_deps)
        )


# ---------- statement dispatch ----------

def _inner_assignment(decl: Node) -> Node | None:
    """`local T = {}` wraps its assignment; a bare `local T` has none."""
    return next((c for c in decl.named_children if c.type == "assignment_statement"), None)


def _visit_assignment(
    assign: Node | None,
    tag_node: Node,
    source: bytes,
    candidates: dict[str, _Candidate],
) -> None:
    """Handle `T = {}`, `T.__index = T`, `T.field = value`.

    `tag_node` is the statement a `---@cdec` comment would sit above — the outer
    `variable_declaration` for a `local`, the assignment itself otherwise.
    """
    if assign is None:
        return
    targets = next((c for c in assign.named_children if c.type == "variable_list"), None)
    values = next((c for c in assign.named_children if c.type == "expression_list"), None)
    if targets is None:
        return

    for i, target in enumerate(targets.named_children):
        value = values.named_children[i] if values and i < len(values.named_children) else None

        if target.type == "identifier":
            name = _text(target, source)
            if value is not None and _is_table_like(value):
                cand = _candidate(candidates, name, tag_node)
                cand.decl_nodes.append(tag_node)
                base = _metatable_base(value, source)
                if base:
                    cand.base = base
            continue

        if target.type == "dot_index_expression":
            owner, field = _dot_parts(target, source)
            if not owner or not field:
                continue
            cand = _candidate(candidates, owner, tag_node)
            if field == "__index":
                cand.self_indexed = True
                cand.decl_nodes.append(tag_node)
                continue
            if field in _METAFIELDS:
                continue
            cand.static_attrs.append(
                Attribute(
                    name=field,
                    type="",
                    visibility=_visibility(field),
                    is_static=True,
                    default=_text(value, source) if value is not None else None,
                )
            )


def _visit_setmetatable_call(stmt: Node, source: bytes, candidates: dict[str, _Candidate]) -> None:
    """`setmetatable(Child, { __index = Base })` as a bare statement."""
    callee = next((c for c in stmt.named_children if c.type == "identifier"), None)
    if callee is None or _text(callee, source) != "setmetatable":
        return
    args = next((c for c in stmt.named_children if c.type == "arguments"), None)
    if args is None:
        return
    named = args.named_children
    if len(named) < 2 or named[0].type != "identifier":
        return
    base = _index_field(named[1], source)
    if base:
        _candidate(candidates, _text(named[0], source), stmt).base = base


def _visit_function(
    node: Node,
    source: bytes,
    candidates: dict[str, _Candidate],
    free_functions: list[Operation],
    free_deps: list[str],
) -> None:
    target = next(
        (
            c
            for c in node.children
            if c.type in ("identifier", "dot_index_expression", "method_index_expression")
        ),
        None,
    )
    if target is None:
        return

    deps = _body_type_refs(node, source)

    if target.type == "identifier":
        free_functions.append(_operation(node, _text(target, source), True, source))
        free_deps.extend(deps)
        return

    owner, name = _dot_parts(target, source)
    if not owner or not name:
        return
    # `function T.m()` is a static/class function; `function T:m()` takes an
    # implicit `self` and is an instance method.
    is_static = target.type == "dot_index_expression"
    cand = _candidate(candidates, owner, node)
    cand.operations.append(_operation(node, name, is_static, source))
    cand.deps.extend(deps)
    if not is_static:
        cand.instance_attrs.extend(_self_fields(node, source))
    else:
        # A constructor is written `function T.new()`, so its `self.x = ...`
        # assignments are the instance attributes too.
        cand.instance_attrs.extend(_self_fields(node, source))


# ---------- building ----------

def _candidate(candidates: dict[str, _Candidate], name: str, node: Node) -> _Candidate:
    existing = candidates.get(name)
    if existing is None:
        existing = _Candidate(name, node.start_point[0] + 1)
        candidates[name] = existing
    return existing


def _to_class(cand: _Candidate, package_qn: str, source: bytes, file_str: str) -> Class | None:
    rules = rules_for_statements(cand.decl_nodes, source)
    is_class = bool(cand.operations or cand.self_indexed or cand.base or rules)
    if not is_class:
        return None

    qn = f"{package_qn}.{cand.name}" if package_qn != "__root__" else cand.name
    attributes = list(cand.static_attrs)
    known = {a.name for a in attributes}
    for field in cand.instance_attrs:
        if field in known:
            continue
        known.add(field)
        attributes.append(Attribute(name=field, type="", visibility=_visibility(field)))

    return Class(
        name=cand.name,
        qualified_name=qn,
        kind="class",
        attributes=attributes,
        operations=cand.operations,
        bases=[cand.base] if cand.base else [],
        location=SourceLocation(file=file_str, start_line=cand.line, end_line=cand.line),
        rules=rules,
        dependencies=_dedupe(cand.deps, drop=cand.name),
    )


def _module_class(
    stem: str,
    package_qn: str,
    file_str: str,
    operations: list[Operation],
    deps: list[str],
) -> Class:
    qn = f"{package_qn}.{stem}" if package_qn != "__root__" else stem
    return Class(
        name=stem,
        qualified_name=qn,
        kind="static",
        operations=operations,
        location=SourceLocation(file=file_str, start_line=1, end_line=1),
        description=f"File-scope functions declared in {file_str}.",
        dependencies=_dedupe(deps, drop=stem),
    )


def _operation(node: Node, name: str, is_static: bool, source: bytes) -> Operation:
    return Operation(
        name=name,
        parameters=_parameters(node, source),
        visibility=_visibility(name),
        is_static=is_static,
        rules=extract_rules(node, source),
    )


def _parameters(node: Node, source: bytes) -> list[Parameter]:
    params = next((c for c in node.children if c.type == "parameters"), None)
    if params is None:
        return []
    out: list[Parameter] = []
    for child in params.named_children:
        if child.type == "identifier":
            out.append(Parameter(name=_text(child, source)))
        elif child.type == "vararg_expression":
            out.append(Parameter(name="..."))
    return out


# ---------- expression helpers ----------

def _is_table_like(value: Node) -> bool:
    """`{}` directly, or a `setmetatable(...)` call producing one."""
    if value.type == "table_constructor":
        return True
    return value.type == "function_call" and value.child_count > 0


def _metatable_base(value: Node, source: bytes) -> str:
    """Base class from `setmetatable({}, { __index = Base })`."""
    if value.type != "function_call":
        return ""
    callee = next((c for c in value.named_children if c.type == "identifier"), None)
    if callee is None or _text(callee, source) != "setmetatable":
        return ""
    args = next((c for c in value.named_children if c.type == "arguments"), None)
    if args is None:
        return ""
    named = args.named_children
    return _index_field(named[1], source) if len(named) >= 2 else ""


def _index_field(table: Node, source: bytes) -> str:
    """The `Base` in a `{ __index = Base }` metatable literal."""
    if table.type == "identifier":
        return _text(table, source)
    if table.type != "table_constructor":
        return ""
    for entry in table.named_children:
        if entry.type != "field":
            continue
        parts = [c for c in entry.named_children]
        if len(parts) >= 2 and _text(parts[0], source) == "__index":
            return _text(parts[1], source)
    return ""


def _dot_parts(node: Node, source: bytes) -> tuple[str, str]:
    """`T.m` / `T:m` -> ("T", "m"). Nested paths keep only the last two hops."""
    idents = [c for c in node.named_children if c.type in ("identifier", "dot_index_expression")]
    if len(idents) < 2:
        return "", ""
    owner_node, name_node = idents[0], idents[-1]
    owner = _text(owner_node, source)
    return owner.rsplit(".", 1)[-1] if "." in owner else owner, _text(name_node, source)


def _self_fields(node: Node, source: bytes) -> list[str]:
    """Field names assigned via `self.x = ...` anywhere in a function body."""
    block = next((c for c in node.children if c.type == "block"), None)
    if block is None:
        return []
    out: list[str] = []

    # Walked in source order (not with a LIFO stack) so the attribute list keeps
    # the order the constructor assigns them in — that order is what renders in
    # the class box and what the diff compares.
    def walk(current: Node) -> None:
        if current.type == "assignment_statement":
            targets = next(
                (c for c in current.named_children if c.type == "variable_list"), None
            )
            if targets is not None:
                for target in targets.named_children:
                    if target.type != "dot_index_expression":
                        continue
                    owner, field = _dot_parts(target, source)
                    if owner == "self" and field and field not in out:
                        out.append(field)
        for child in current.children:
            walk(child)

    walk(block)
    return out


def _body_type_refs(node: Node, source: bytes) -> list[str]:
    """Capitalised identifiers used in a function body — candidate type refs.

    Heuristic, like the C# and Odin parsers: `resolve_association` keeps only the
    ones matching a project class, so locals and stdlib names drop out. Only the
    block is walked, so parameter names and `---@cdec` comments never leak in.
    """
    block = next((c for c in node.children if c.type == "block"), None)
    if block is None:
        return []
    out: list[str] = []
    seen: set[str] = set()
    stack = [block]
    while stack:
        current = stack.pop()
        stack.extend(current.children)
        if current.type != "identifier":
            continue
        text = _text(current, source)
        if text and text[0].isupper() and text not in seen:
            seen.add(text)
            out.append(text)
    return out


# ---------- packages / misc ----------

def _qualified_package_name(rel_file: Path) -> str:
    parts = list(rel_file.parts[:-1])
    return ".".join(parts) if parts else "__root__"


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
    if len(parts) == 1:
        pkg = Package(name=parts[0], qualified_name=qualified_name)
        project.packages.append(pkg)
    else:
        parent = _ensure_package(project, ".".join(parts[:-1]), index)
        pkg = Package(name=parts[-1], qualified_name=qualified_name)
        parent.sub_packages.append(pkg)
    index[qualified_name] = pkg
    return pkg


def _visibility(name: str) -> Visibility:
    """Leading underscore is Lua's private-by-convention marker."""
    return Visibility.PRIVATE if name.startswith("_") else Visibility.PUBLIC


def _dedupe(refs: list[str], *, drop: str = "") -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for ref in refs:
        if not ref or ref == drop or ref in seen:
            continue
        seen.add(ref)
        out.append(ref)
    return out


def _text(node: Node | None, source: bytes) -> str:
    if node is None:
        return ""
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")
