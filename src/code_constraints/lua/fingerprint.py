"""AST fingerprinting for Lua (`cdec lock`, Engine C).

Digests come from the tree-sitter tree via `core.ts_fingerprint`, so a locked
element survives reformatting and relocation within its file.

Lua-specific concerns:

* **A class is not one node.** The table-plus-metatable idiom spreads a class
  across several top-level statements (`local T = {}`, `T.__index = T`, each
  `function T:m()`), so a class target digests the whole group of statements that
  belong to `T`. That is the right semantics for a freeze: adding a method to a
  locked class is a change to the class.
* **Tags are comments**, so `---@cdec locked` lines are dropped from the digest
  explicitly rather than incidentally — otherwise `include_docstrings` would let
  applying a lock change the very digest it records.
* **Target names match the UML model**, so a target read from `cdec lock list` is
  the target `cdec lock set` accepts. Naming reuses `lua.parser` helpers rather
  than re-deriving them, so the two can't drift apart.
"""

from __future__ import annotations

from pathlib import Path

import tree_sitter_lua
from tree_sitter import Language, Node, Parser

from code_constraints.core.ts_fingerprint import digest_members
from code_constraints.lock.model import LOCK_RULE, LockTarget
from code_constraints.lua.parser import (
    _dot_parts,
    _inner_assignment,
    _qualified_package_name,
    _should_skip,
    _text,
)
from code_constraints.lua.rules_extract import comment_is_rule_tag, extract_rules

DIGEST_ALGO = "lua-ts/1"

_LANG = Language(tree_sitter_lua.language())
_PARSER = Parser(_LANG)


def collect_lockables(
    root: str | Path, *, include_docstrings: bool = False
) -> list[LockTarget]:
    root_path = Path(root).resolve()
    out: list[LockTarget] = []

    for lua_file in sorted(root_path.rglob("*.lua")):
        if _should_skip(lua_file):
            continue
        try:
            source = lua_file.read_bytes()
        except OSError:
            continue
        tree = _PARSER.parse(source)
        rel = lua_file.relative_to(root_path)
        out.extend(
            _collect_file(
                tree.root_node,
                source,
                _qualified_package_name(rel),
                rel,
                include_docstrings,
            )
        )
    return out


def _collect_file(
    root: Node,
    source: bytes,
    package_qn: str,
    rel: Path,
    include_docstrings: bool,
) -> list[LockTarget]:
    file = rel.as_posix()
    # Table name -> the statements that *declare* it (`local T = {}`,
    # `T.__index = T`, `T.field = …`). Kept apart from its function
    # declarations, because a class's own tags come only from these: a
    # `---@cdec locked` above `function T:m()` locks the method, not the class.
    declarations: dict[str, list[Node]] = {}
    # (table, member) -> the function declarations for it.
    methods: dict[tuple[str, str], list[Node]] = {}
    # Tables carrying a self-index or a metatable base — class evidence even
    # with no methods, matching how the parser promotes a table.
    marked: set[str] = set()
    free: dict[str, list[Node]] = {}

    for stmt in root.named_children:
        if stmt.type == "function_declaration":
            target = next(
                (
                    c
                    for c in stmt.children
                    if c.type
                    in ("identifier", "dot_index_expression", "method_index_expression")
                ),
                None,
            )
            if target is None:
                continue
            if target.type == "identifier":
                free.setdefault(_text(target, source), []).append(stmt)
                continue
            owner, name = _dot_parts(target, source)
            if owner and name:
                declarations.setdefault(owner, [])
                methods.setdefault((owner, name), []).append(stmt)
            continue

        assign = _inner_assignment(stmt) if stmt.type == "variable_declaration" else (
            stmt if stmt.type == "assignment_statement" else None
        )
        if assign is None:
            continue
        for name, is_marker in _assigned_tables(assign, source):
            declarations.setdefault(name, []).append(stmt)
            if is_marker:
                marked.add(name)

    out: list[LockTarget] = []
    for table, decls in declarations.items():
        member_nodes = [
            node for (owner, _name), nodes in methods.items() if owner == table
            for node in nodes
        ]
        rules = [r for node in decls for r in extract_rules(node, source)]
        # Mirror the parser's promotion rule: a bare `local cfg = {}` data table
        # is not a class, so it is not a lockable either.
        if not (member_nodes or table in marked or rules):
            continue
        qn = f"{package_qn}.{table}" if package_qn != "__root__" else table
        statements = sorted(decls + member_nodes, key=lambda n: n.start_byte)
        out.append(
            _target(
                [(node, source) for node in statements],
                qn,
                "class",
                file,
                include_docstrings,
                tag_nodes=decls,
            )
        )

    for (table, name), nodes in methods.items():
        owner = f"{package_qn}.{table}" if package_qn != "__root__" else table
        out.append(
            _target(
                [(node, source) for node in nodes],
                f"{owner}.{name}",
                "method",
                file,
                include_docstrings,
            )
        )

    for name, nodes in free.items():
        owner = f"{package_qn}.{rel.stem}" if package_qn != "__root__" else rel.stem
        out.append(
            _target(
                [(node, source) for node in nodes],
                f"{owner}.{name}",
                "function",
                file,
                include_docstrings,
            )
        )

    return out


def _assigned_tables(assign: Node, source: bytes) -> list[tuple[str, bool]]:
    """Table names an assignment contributes to, each with a "this is class
    evidence" flag.

    `T = {}` names `T` but proves nothing on its own; `T.__index = …` and
    `T = setmetatable(…)` are the metatable markers that make it a prototype.
    """
    targets = next((c for c in assign.named_children if c.type == "variable_list"), None)
    if targets is None:
        return []
    values = next((c for c in assign.named_children if c.type == "expression_list"), None)
    out: list[tuple[str, bool]] = []
    for i, target in enumerate(targets.named_children):
        value = values.named_children[i] if values and i < len(values.named_children) else None
        if target.type == "identifier":
            marker = value is not None and _is_setmetatable(value, source)
            out.append((_text(target, source), marker))
        elif target.type == "dot_index_expression":
            owner, field = _dot_parts(target, source)
            if owner:
                out.append((owner, field == "__index"))
    return out


def _is_setmetatable(value: Node, source: bytes) -> bool:
    if value.type != "function_call":
        return False
    callee = next((c for c in value.named_children if c.type == "identifier"), None)
    return callee is not None and _text(callee, source) == "setmetatable"


def _target(
    members: list[tuple[Node, bytes]],
    target: str,
    kind: str,
    file: str,
    include_docstrings: bool,
    tag_nodes: list[Node] | None = None,
) -> LockTarget:
    """`tag_nodes` narrows where the `@locked` tag may be read from.

    A class digests its methods as well as its declaration statements, but a tag
    above `function T:m()` locks the *method*; only tags above the declaration
    statements lock the class.
    """

    def drop(node: Node, source: bytes) -> bool:
        if node.type != "comment":
            return False
        # A rule tag is never part of the implementation, whatever the docstring
        # setting: applying or removing `---@cdec locked` must leave the digest
        # of the body it guards untouched.
        if comment_is_rule_tag(node, source):
            return True
        return not include_docstrings

    declared = False
    params: dict[str, str] = {}
    source = members[0][1]
    tagged = (
        [(node, source) for node in tag_nodes] if tag_nodes is not None else members
    )
    for node, source in tagged:
        for rule in extract_rules(node, source):
            if rule.name == LOCK_RULE:
                declared = True
                params = {**rule.kwargs, **params} if params else dict(rule.kwargs)

    return LockTarget(
        target=target,
        kind=kind,  # type: ignore[arg-type]
        digest=digest_members(members, drop),
        algo=DIGEST_ALGO,
        file=file,
        line=members[0][0].start_point[0] + 1,
        declared=declared,
        params=params,
    )
