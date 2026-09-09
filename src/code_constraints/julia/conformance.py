"""Body-level conformance analysis for Julia (`cdec enforce`, Engine B).

Re-parses Julia source with tree-sitter and inspects function bodies for
violations of architectural-rule tags. Reuses `julia.rules_extract` so "what is a
rule" stays identical to the UML parser, and `core.receivers.resolve_owner` so a
function is attributed to the same struct the model shows.

Detection sits between the Python analyzer's guesswork and the C# analyzer's
precision, because of one Julia fact: **construction has no dedicated syntax**.
`Money(1.0)` is an ordinary call, indistinguishable at the grammar level from
`round(1.0)`. So a call counts as a construction only when its callee is the
name of a type *in this project* — the parser already collected them. That is
narrower than Python's "callee is Capitalised" heuristic and produces no false
positives on stdlib calls, at the cost of missing constructions of types the
parse didn't see.

Field reassignment (`immutable`) is precise: an `assignment` whose target is a
`field_expression` rooted at the receiver argument. Note that a non-`mutable
struct` is already immutable to the compiler; the tag earns its keep on
`mutable struct`, where it says the mutability is an implementation detail.
"""

from __future__ import annotations

from pathlib import Path

import tree_sitter_julia
from tree_sitter import Language, Node, Parser

from code_constraints.core.annotations import literal_set
from code_constraints.core.model import Project, RuleAnnotation
from code_constraints.core.receivers import resolve_owner
from code_constraints.enforce.model import Finding
from code_constraints.julia.parser import (
    _TYPE_DEFINITION_TYPES,
    _base_name,
    _is_short_function,
    _operation,
    _qualified_package_name,
    _should_skip,
    _text,
    _type_head_parts,
)
from code_constraints.julia.rules_extract import unwrap_macros, using_has_shim

_LANG = Language(tree_sitter_julia.language())
_PARSER = Parser(_LANG)

CTOR_RULE = "no-instantiation"
FACTORY_RULE = "factory"
IMMUTABLE_RULE = "immutable"


def analyze(root: Path, project: Project) -> list[Finding]:
    project_classes = {cls.name for cls in project.iter_classes()}
    factory_index = _factory_index(project)
    class_rules = {
        cls.qualified_name: {r.name: r for r in cls.rules}
        for cls in project.iter_classes()
    }

    struct_index: dict[tuple[str, str], str] = {}
    functions: list[tuple[Node, bytes, str, str, bool]] = []

    for jl_file in sorted(root.rglob("*.jl")):
        if _should_skip(jl_file):
            continue
        try:
            source = jl_file.read_bytes()
        except OSError:
            continue
        tree = _PARSER.parse(source)
        rel = jl_file.relative_to(root)
        shim = using_has_shim(tree.root_node, source)
        _scan(
            tree.root_node, source, _qualified_package_name(rel),
            rel.as_posix(), shim, struct_index, functions,
        )

    findings: list[Finding] = []
    for node, source, package_qn, file, shim in functions:
        _analyze_function(
            node, source, package_qn, file, shim, struct_index,
            class_rules, project_classes, factory_index, findings,
        )
    return findings


def _scan(
    parent: Node,
    source: bytes,
    package_qn: str,
    file: str,
    shim: bool,
    struct_index: dict[tuple[str, str], str],
    functions: list[tuple[Node, bytes, str, str, bool]],
) -> None:
    for child in parent.named_children:
        _rules, node = unwrap_macros(child, source, shim)
        if node is None:
            continue
        if node.type == "module_definition":
            ident = next((c for c in node.children if c.type == "identifier"), None)
            name = _text(ident, source) if ident is not None else "anon"
            nested = f"{package_qn}.{name}" if package_qn != "__root__" else name
            _scan(node, source, nested, file, shim, struct_index, functions)
        elif node.type in _TYPE_DEFINITION_TYPES:
            head = next((c for c in node.children if c.type == "type_head"), None)
            if head is None:
                continue
            name, _bases = _type_head_parts(head, source)
            if name:
                struct_index[(package_qn, name)] = (
                    f"{package_qn}.{name}" if package_qn != "__root__" else name
                )
        elif node.type == "function_definition" or _is_short_function(node):
            functions.append((child, source, package_qn, file, shim))


def _analyze_function(
    member: Node,
    source: bytes,
    package_qn: str,
    file: str,
    shim: bool,
    struct_index: dict[tuple[str, str], str],
    class_rules: dict[str, dict[str, RuleAnnotation]],
    project_classes: set[str],
    factory_index: dict[str, set[str]],
    out: list[Finding],
) -> None:
    rules, definition = unwrap_macros(member, source, shim)
    if definition is None:
        return
    operation = _operation(definition, rules, source)
    if operation is None:
        return

    owner_qn = resolve_owner(
        _base_name(operation.parameters[0].type) if operation.parameters else "",
        package_qn,
        struct_index,
    )
    if owner_qn is None:
        stem = Path(file).stem
        owner_qn = f"{package_qn}.{stem}" if package_qn != "__root__" else stem
        owner_name = stem
        receiver = ""
    else:
        owner_name = owner_qn.rsplit(".", 1)[-1]
        receiver = operation.parameters[0].name

    func_rules = {r.name: r for r in rules}
    owner_rules = class_rules.get(owner_qn, {})
    name = operation.name

    noinst = func_rules.get(CTOR_RULE, owner_rules.get(CTOR_RULE))
    allow = literal_set(noinst.kwargs.get("allow", "")) if noinst is not None else None

    for constructed, line in _constructions(definition, source, project_classes):
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
                        f"'{owner_qn}.{name}' is tagged @no_instantiation but "
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

    if IMMUTABLE_RULE in owner_rules and receiver:
        for field, line in _receiver_assignments(definition, receiver, source):
            out.append(
                Finding(
                    rule=IMMUTABLE_RULE,
                    qualified_name=owner_qn,
                    message=(
                        f"'{owner_qn}' is tagged @immutable but '{name}' reassigns "
                        f"field '{field}'."
                    ),
                    detail=f"{name}.{field}",
                    file=file,
                    line=line,
                )
            )


def _body_nodes(definition: Node) -> list[Node]:
    """The definition's body, excluding its signature.

    Walking the whole node would read parameter type annotations as
    constructions — `f(m::Money)` is not a call to `Money`.
    """
    signature = next((c for c in definition.children if c.type == "signature"), None)
    if signature is not None:
        return [c for c in definition.named_children if c is not signature]
    if definition.type == "assignment":
        # Short form `f(x::T) = <body>`: everything right of the `=`.
        named = definition.named_children
        return list(named[1:]) if len(named) > 1 else []
    return list(definition.named_children)


def _constructions(
    definition: Node, source: bytes, project_classes: set[str]
) -> list[tuple[str, int]]:
    """Calls in the body whose callee names a type defined in this project."""
    out: list[tuple[str, int]] = []
    for start in _body_nodes(definition):
        stack = [start]
        while stack:
            node = stack.pop()
            stack.extend(node.children)
            if node.type != "call_expression":
                continue
            callee = node.named_children[0] if node.named_children else None
            if callee is None:
                continue
            name = _base_name(_text(callee, source))
            if name in project_classes:
                out.append((name, node.start_point[0] + 1))
    return out


def _receiver_assignments(
    definition: Node, receiver: str, source: bytes
) -> list[tuple[str, int]]:
    """`recv.field = …` assignments inside the body."""
    out: list[tuple[str, int]] = []
    for start in _body_nodes(definition):
        stack = [start]
        while stack:
            node = stack.pop()
            stack.extend(node.children)
            if node.type != "assignment":
                continue
            target = node.named_children[0] if node.named_children else None
            if target is None or target.type != "field_expression":
                continue
            parts = [c for c in target.children if c.type == "identifier"]
            if len(parts) >= 2 and _text(parts[0], source) == receiver:
                out.append((_text(parts[-1], source), node.start_point[0] + 1))
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
