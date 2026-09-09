"""Body-level conformance analysis for C# (`cdec enforce`, Engine B).

Re-parses C# source with tree-sitter and inspects method/constructor bodies for
violations of architectural-rule tags. Reuses the shared recognizer in
`rules_extract` so the set of "what is a rule" stays identical to the UML parser.

Unlike the Python analyzer, construction detection is precise: it keys off the
`object_creation_expression` / `array_creation_expression` node kinds rather than
guessing from the callee name. Field reassignment (`immutable`) is matched on
`this.<field>` member access and bare assignment to a known field outside the
constructor.
"""

from __future__ import annotations

import re
from pathlib import Path

import tree_sitter_c_sharp
from tree_sitter import Language, Node, Parser

from code_constraints.core.model import Project
from code_constraints.csharp.rules_extract import extract_rules, using_has_shim
from code_constraints.enforce.model import Finding

_LANG = Language(tree_sitter_c_sharp.language())
_PARSER = Parser(_LANG)

CTOR_RULE = "no-instantiation"
FACTORY_RULE = "factory"
IMMUTABLE_RULE = "immutable"

_CLASS_LIKE = {
    "class_declaration",
    "interface_declaration",
    "struct_declaration",
    "record_declaration",
    "record_struct_declaration",
}
_SKIP_DIR_NAMES = {"bin", "obj", ".git", "packages", "TestResults"}


def analyze(root: Path, project: Project) -> list[Finding]:
    project_classes = {cls.name for cls in project.iter_classes()}
    factory_index = _factory_index(project)

    findings: list[Finding] = []
    for cs_file in sorted(root.rglob("*.cs")):
        if any(part in _SKIP_DIR_NAMES for part in cs_file.parts):
            continue
        try:
            source = cs_file.read_bytes()
        except OSError:
            continue
        tree = _PARSER.parse(source)
        rel = cs_file.relative_to(root).as_posix()
        shim = using_has_shim(tree.root_node, source)
        for cls_node, qn, short_name in _iter_classes(tree.root_node, source):
            _analyze_class(
                cls_node, qn, short_name, rel, source, shim,
                project_classes, factory_index, findings,
            )
    return findings


def _analyze_class(
    cls_node: Node,
    class_qn: str,
    class_name: str,
    file: str,
    source: bytes,
    shim: bool,
    project_classes: set[str],
    factory_index: dict[str, set[str]],
    out: list[Finding],
) -> None:
    crules = _rule_map(cls_node, source, shim)
    class_noinst = _allow_set(crules[CTOR_RULE]) if CTOR_RULE in crules else None
    is_immutable = IMMUTABLE_RULE in crules
    field_names = _field_names(cls_node, source)

    body = cls_node.child_by_field_name("body")
    if body is None:
        return
    for member in body.named_children:
        if member.type not in ("method_declaration", "constructor_declaration"):
            continue
        is_ctor = member.type == "constructor_declaration"
        mrules = _rule_map(member, source, shim)
        if CTOR_RULE in mrules:
            noinst_allow = _allow_set(mrules[CTOR_RULE])
        else:
            noinst_allow = class_noinst
        name = _member_name(member, source)
        body_nodes = _body_nodes(member)

        for callee, line in _constructions(body_nodes, source):
            is_construction = callee in project_classes or callee[:1].isupper()
            if noinst_allow is not None and is_construction and callee not in noinst_allow:
                out.append(
                    Finding(
                        rule=CTOR_RULE,
                        qualified_name=class_qn,
                        message=(
                            f"'{class_qn}.{name}' is tagged [NoInstantiation] but "
                            f"constructs '{callee}'."
                        ),
                        detail=f"{name}->{callee}",
                        file=file,
                        line=line,
                    )
                )
            designated = factory_index.get(callee)
            if designated is not None and class_name not in designated:
                allowed = ", ".join(sorted(designated)) or "(none)"
                out.append(
                    Finding(
                        rule=FACTORY_RULE,
                        qualified_name=class_qn,
                        message=(
                            f"'{class_qn}.{name}' constructs '{callee}' outside its "
                            f"designated factory ({allowed})."
                        ),
                        detail=f"{name}->{callee}",
                        file=file,
                        line=line,
                    )
                )

        if is_immutable and not is_ctor:
            for field_name, line in _field_assignments(body_nodes, field_names, source):
                out.append(
                    Finding(
                        rule=IMMUTABLE_RULE,
                        qualified_name=class_qn,
                        message=(
                            f"'{class_qn}' is [Immutable] but '{name}' reassigns field "
                            f"'{field_name}' outside the constructor."
                        ),
                        detail=f"{name}.{field_name}",
                        file=file,
                        line=line,
                    )
                )


def _factory_index(project: Project) -> dict[str, set[str]]:
    """Created-type name -> set of class names designated to construct it."""
    idx: dict[str, set[str]] = {}
    for cls in project.iter_classes():
        rule_sources = list(cls.rules) + [r for op in cls.operations for r in op.rules]
        for rule in rule_sources:
            if rule.name != FACTORY_RULE:
                continue
            for created in _str_list(_get_kwarg(rule.kwargs, "creates")):
                idx.setdefault(created, set()).add(cls.name)
    return idx


def _iter_classes(root: Node, source: bytes) -> list[tuple[Node, str, str]]:
    results: list[tuple[Node, str, str]] = []
    file_scoped: str | None = None
    for child in root.named_children:
        if child.type == "namespace_declaration":
            _collect_ns(child, "", source, results)
        elif child.type == "file_scoped_namespace_declaration":
            name_node = child.child_by_field_name("name")
            file_scoped = _text(name_node, source) if name_node else "anon"
        elif child.type in _CLASS_LIKE:
            _collect_class(child, file_scoped or "", source, results)
    return results


def _collect_ns(
    node: Node, parent_qn: str, source: bytes, results: list[tuple[Node, str, str]]
) -> None:
    name_node = node.child_by_field_name("name")
    name = _text(name_node, source) if name_node else "anon"
    qn = name if not parent_qn else f"{parent_qn}.{name}"
    body = node.child_by_field_name("body")
    if body is None:
        return
    for child in body.named_children:
        if child.type == "namespace_declaration":
            _collect_ns(child, qn, source, results)
        elif child.type in _CLASS_LIKE:
            _collect_class(child, qn, source, results)


def _collect_class(
    node: Node, package_qn: str, source: bytes, results: list[tuple[Node, str, str]]
) -> None:
    name_node = node.child_by_field_name("name")
    if name_node is None:
        return
    name = _text(name_node, source)
    qn = f"{package_qn}.{name}" if package_qn else name
    results.append((node, qn, name))


def _rule_map(node: Node, source: bytes, shim: bool) -> dict[str, object]:
    return {r.name: r for r in extract_rules(node, source, shim)}


def _allow_set(rule) -> set[str]:
    if rule is None:
        return set()
    return _str_list(_get_kwarg(rule.kwargs, "allow"))


def _get_kwarg(kwargs: dict[str, str], name: str) -> str:
    """Case-insensitive kwarg lookup (C# uses PascalCase `Allow`/`Creates`)."""
    for k, v in kwargs.items():
        if k.lower() == name.lower():
            return v
    return ""


def _str_list(source_text: str) -> set[str]:
    """Pull quoted strings out of a C# array literal, e.g.
    'new[] { "List" }' -> {"List"}. Tolerant: returns {} on no match."""
    if not source_text:
        return set()
    return set(re.findall(r'"([^"]*)"', source_text))


def _member_name(node: Node, source: bytes) -> str:
    name_node = node.child_by_field_name("name")
    return _text(name_node, source) if name_node else "<ctor>"


def _body_nodes(method: Node) -> list[Node]:
    """The block and/or arrow-expression body of a method, excluding its
    attribute_list (so a `new[] { ... }` inside `[NoInstantiation(...)]` is
    never mistaken for a construction)."""
    out: list[Node] = []
    seen: set[int] = set()
    # For arrow-bodied methods the "body" field IS the arrow_expression_clause,
    # so guard against collecting it twice.
    block = method.child_by_field_name("body")
    if block is not None:
        out.append(block)
        seen.add(block.id)
    for c in method.children:
        if c.type == "arrow_expression_clause" and c.id not in seen:
            out.append(c)
    return out


def _constructions(body_nodes: list[Node], source: bytes) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    stack = list(body_nodes)
    while stack:
        n = stack.pop()
        if n.type in ("object_creation_expression", "array_creation_expression"):
            name = _type_name(n.child_by_field_name("type"), source)
            if name:
                out.append((name, n.start_point[0] + 1))
        stack.extend(n.children)
    return out


def _type_name(type_node: Node | None, source: bytes) -> str:
    if type_node is None:
        return ""
    text = _text(type_node, source)
    text = text.split("<", 1)[0]
    return text.rsplit(".", 1)[-1].strip()


def _field_assignments(
    body_nodes: list[Node], field_names: set[str], source: bytes
) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    stack = list(body_nodes)
    while stack:
        n = stack.pop()
        if n.type == "assignment_expression":
            field = _assign_target_field(n.child_by_field_name("left"), field_names, source)
            if field:
                out.append((field, n.start_point[0] + 1))
        stack.extend(n.children)
    return out


def _assign_target_field(
    left: Node | None, field_names: set[str], source: bytes
) -> str | None:
    if left is None:
        return None
    if left.type == "member_access_expression":
        obj = left.child_by_field_name("expression")
        name = left.child_by_field_name("name")
        if obj is not None and obj.type == "this" and name is not None:
            return _text(name, source)
    if left.type == "identifier":
        text = _text(left, source)
        if text in field_names:
            return text
    return None


def _field_names(cls_node: Node, source: bytes) -> set[str]:
    names: set[str] = set()
    body = cls_node.child_by_field_name("body")
    if body is None:
        return names
    for member in body.named_children:
        if member.type == "field_declaration":
            decl = next(
                (c for c in member.named_children if c.type == "variable_declaration"),
                None,
            )
            if decl is None:
                continue
            for d in decl.named_children:
                if d.type == "variable_declarator":
                    nn = d.child_by_field_name("name")
                    if nn is not None:
                        names.add(_text(nn, source))
        elif member.type == "property_declaration":
            nn = member.child_by_field_name("name")
            if nn is not None:
                names.add(_text(nn, source))
    return names


def _text(node: Node | None, source: bytes) -> str:
    if node is None:
        return ""
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")
