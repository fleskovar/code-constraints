"""Body-level conformance analysis for Lua (`cdec enforce`, Engine B).

Re-parses Lua source with tree-sitter and inspects function bodies for violations
of architectural-rule tags. Reuses `lua.rules_extract` so "what is a rule" stays
identical to the UML parser.

Lua is the loosest of the supported languages, so detection is explicitly
heuristic — closer to the Python analyzer than to the C# one:

* **Construction** has no syntax of its own. Two idioms are recognised:
  `T.new(...)` / `T:new(...)` where `T` names a class in the project, and a
  direct `setmetatable(tbl, T)`. A bare `T(...)` call is *not* treated as
  construction, because in Lua that is an ordinary `__call`, not a constructor.
* **Field reassignment** is `self.x = …` outside the constructor. "The
  constructor" means a static function on the class named `new`, `create` or
  `init` — Lua has no `__init__` to privilege, so the convention is named
  explicitly here rather than guessed per project.

`allow` is the escape hatch when the heuristic is wrong, exactly as in Python.
"""

from __future__ import annotations

from pathlib import Path

import tree_sitter_lua
from tree_sitter import Language, Node, Parser

from code_constraints.core.annotations import literal_set
from code_constraints.core.model import Project, RuleAnnotation
from code_constraints.enforce.model import Finding
from code_constraints.lua.parser import (
    _dot_parts,
    _qualified_package_name,
    _should_skip,
    _text,
)
from code_constraints.lua.rules_extract import extract_rules

_LANG = Language(tree_sitter_lua.language())
_PARSER = Parser(_LANG)

CTOR_RULE = "no-instantiation"
FACTORY_RULE = "factory"
IMMUTABLE_RULE = "immutable"

# Function names treated as constructors: `self.x = …` in these is initialisation,
# not reassignment.
_CONSTRUCTOR_NAMES = frozenset({"new", "create", "init", "_init", "_new"})


def analyze(root: Path, project: Project) -> list[Finding]:
    project_classes = {cls.name for cls in project.iter_classes()}
    factory_index = _factory_index(project)
    class_rules = {
        cls.qualified_name: {r.name: r for r in cls.rules}
        for cls in project.iter_classes()
    }

    findings: list[Finding] = []
    for lua_file in sorted(root.rglob("*.lua")):
        if _should_skip(lua_file):
            continue
        try:
            source = lua_file.read_bytes()
        except OSError:
            continue
        tree = _PARSER.parse(source)
        rel = lua_file.relative_to(root)
        package_qn = _qualified_package_name(rel)
        for stmt in tree.root_node.named_children:
            if stmt.type != "function_declaration":
                continue
            _analyze_function(
                stmt, source, package_qn, rel, class_rules,
                project_classes, factory_index, findings,
            )
    return findings


def _analyze_function(
    node: Node,
    source: bytes,
    package_qn: str,
    rel: Path,
    class_rules: dict[str, dict[str, RuleAnnotation]],
    project_classes: set[str],
    factory_index: dict[str, set[str]],
    out: list[Finding],
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
    block = next((c for c in node.children if c.type == "block"), None)
    if block is None:
        return

    if target.type == "identifier":
        owner_name = rel.stem
        name = _text(target, source)
    else:
        owner_name, name = _dot_parts(target, source)
        if not owner_name or not name:
            return
    owner_qn = (
        f"{package_qn}.{owner_name}" if package_qn != "__root__" else owner_name
    )

    func_rules = {r.name: r for r in extract_rules(node, source)}
    owner_rules = class_rules.get(owner_qn, {})
    file = rel.as_posix()

    noinst = func_rules.get(CTOR_RULE, owner_rules.get(CTOR_RULE))
    allow = literal_set(noinst.kwargs.get("allow", "")) if noinst is not None else None

    for constructed, line in _constructions(block, source, project_classes):
        if constructed == owner_name:
            # A type constructing itself is never a violation: it is how the
            # `T.new(...)` / inner-constructor idiom is written, and neither
            # `no_instantiation` nor `factory` is aimed at a type's own
            # constructor — they guard construction by *other* code.
            continue
        if allow is not None and constructed not in allow:
            out.append(
                Finding(
                    rule=CTOR_RULE,
                    qualified_name=owner_qn,
                    message=(
                        f"'{owner_qn}.{name}' is tagged @cdec no_instantiation but "
                        f"constructs '{constructed}'."
                    ),
                    detail=f"{name}->{constructed}",
                    file=file,
                    line=line,
                )
            )
        designated = factory_index.get(constructed)
        if designated is not None and owner_name not in designated:
            allowed = ", ".join(sorted(designated)) or "(none)"
            out.append(
                Finding(
                    rule=FACTORY_RULE,
                    qualified_name=owner_qn,
                    message=(
                        f"'{owner_qn}.{name}' constructs '{constructed}' outside its "
                        f"designated factory ({allowed})."
                    ),
                    detail=f"{name}->{constructed}",
                    file=file,
                    line=line,
                )
            )

    if IMMUTABLE_RULE in owner_rules and name not in _CONSTRUCTOR_NAMES:
        for field, line in _self_assignments(block, source):
            out.append(
                Finding(
                    rule=IMMUTABLE_RULE,
                    qualified_name=owner_qn,
                    message=(
                        f"'{owner_qn}' is tagged @cdec immutable but '{name}' "
                        f"reassigns field 'self.{field}'."
                    ),
                    detail=f"{name}.{field}",
                    file=file,
                    line=line,
                )
            )


def _constructions(
    block: Node, source: bytes, project_classes: set[str]
) -> list[tuple[str, int]]:
    """`T.new(...)` / `T:new(...)` calls and `setmetatable(t, T)` allocations."""
    out: list[tuple[str, int]] = []
    stack = [block]
    while stack:
        node = stack.pop()
        stack.extend(node.children)
        if node.type != "function_call":
            continue
        line = node.start_point[0] + 1
        callee = node.named_children[0] if node.named_children else None
        if callee is None:
            continue

        if callee.type in ("dot_index_expression", "method_index_expression"):
            owner, member = _dot_parts(callee, source)
            if owner in project_classes and member in _CONSTRUCTOR_NAMES:
                out.append((owner, line))
            continue

        if callee.type == "identifier" and _text(callee, source) == "setmetatable":
            args = next((c for c in node.named_children if c.type == "arguments"), None)
            named = args.named_children if args else []
            if len(named) >= 2 and named[1].type == "identifier":
                metatable = _text(named[1], source)
                if metatable in project_classes:
                    out.append((metatable, line))
    return out


def _self_assignments(block: Node, source: bytes) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    stack = [block]
    while stack:
        node = stack.pop()
        stack.extend(node.children)
        if node.type != "assignment_statement":
            continue
        targets = next((c for c in node.named_children if c.type == "variable_list"), None)
        if targets is None:
            continue
        for target in targets.named_children:
            if target.type != "dot_index_expression":
                continue
            owner, field = _dot_parts(target, source)
            if owner == "self" and field:
                out.append((field, node.start_point[0] + 1))
    return out


def _factory_index(project: Project) -> dict[str, set[str]]:
    """Created-type name -> set of class names designated to construct it."""
    idx: dict[str, set[str]] = {}
    for cls in project.iter_classes():
        for rule in list(cls.rules) + [r for op in cls.operations for r in op.rules]:
            if rule.name != FACTORY_RULE:
                continue
            for created in literal_set(rule.kwargs.get("creates", "")):
                idx.setdefault(created, set()).add(cls.name)
    return idx
