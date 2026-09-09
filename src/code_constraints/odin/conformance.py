"""Body-level conformance analysis for Odin (`cdec enforce`, Engine B).

Re-parses Odin source with tree-sitter and inspects procedure bodies for
violations of architectural-rule tags. Reuses `odin.rules_extract` so "what is a
rule" stays identical to the UML parser, and `core.receivers.resolve_owner` so a
procedure is attributed to the same struct the model shows.

Detection is precise rather than heuristic, because Odin's grammar distinguishes
the constructs outright:

* **Construction** is a composite literal — grammar node type `struct`, as in
  `Money{amount = 1}` — plus `new(T)` / `make(T)` allocations. There is no need
  to guess from a callee's capitalisation the way the Python analyzer must.
* **Field reassignment** is an `assignment_statement` whose target is a
  `member_expression` rooted at the receiver parameter, so `inv.total = …` is
  caught while an unrelated `other.total = …` is not.

Like the other analyzers this only reports; waiver filtering happens in the
caller.
"""

from __future__ import annotations

from pathlib import Path

import tree_sitter_odin
from tree_sitter import Language, Node, Parser

from code_constraints.core.annotations import literal_set
from code_constraints.core.model import Project, RuleAnnotation
from code_constraints.core.receivers import resolve_owner
from code_constraints.enforce.model import Finding
from code_constraints.odin.parser import (
    _TYPE_DECL_TYPES,
    _package_name,
    _parameters,
    _receiver_name,
    _should_skip,
    _text,
)
from code_constraints.odin.rules_extract import extract_rules

_LANG = Language(tree_sitter_odin.language())
_PARSER = Parser(_LANG)

CTOR_RULE = "no-instantiation"
FACTORY_RULE = "factory"
IMMUTABLE_RULE = "immutable"

# Odin's built-in allocators; the type is their first argument.
_ALLOCATORS = frozenset({"new", "make", "new_clone"})


def analyze(root: Path, project: Project) -> list[Finding]:
    project_classes = {cls.name for cls in project.iter_classes()}
    factory_index = _factory_index(project)
    class_rules = {
        cls.qualified_name: {r.name: r for r in cls.rules}
        for cls in project.iter_classes()
    }

    files: list[tuple[Path, bytes, Node, str]] = []
    struct_index: dict[tuple[str, str], str] = {}

    for odin_file in sorted(root.rglob("*.odin")):
        if _should_skip(odin_file):
            continue
        try:
            source = odin_file.read_bytes()
        except OSError:
            continue
        tree = _PARSER.parse(source)
        rel = odin_file.relative_to(root)
        package_qn = _package_name(tree.root_node, source, rel)
        files.append((rel, source, tree.root_node, package_qn))
        for child in tree.root_node.named_children:
            if child.type not in _TYPE_DECL_TYPES:
                continue
            name_node = next((c for c in child.children if c.type == "identifier"), None)
            if name_node is None:
                continue
            name = _text(name_node, source)
            struct_index[(package_qn, name)] = (
                f"{package_qn}.{name}" if package_qn != "__root__" else name
            )

    findings: list[Finding] = []
    for rel, source, root_node, package_qn in files:
        for child in root_node.named_children:
            if child.type != "procedure_declaration":
                continue
            _analyze_procedure(
                child, source, package_qn, rel.as_posix(), struct_index,
                class_rules, project_classes, factory_index, findings,
            )
    return findings


def _analyze_procedure(
    decl: Node,
    source: bytes,
    package_qn: str,
    file: str,
    struct_index: dict[tuple[str, str], str],
    class_rules: dict[str, dict[str, RuleAnnotation]],
    project_classes: set[str],
    factory_index: dict[str, set[str]],
    out: list[Finding],
) -> None:
    name_node = next((c for c in decl.children if c.type == "identifier"), None)
    proc_node = next((c for c in decl.children if c.type == "procedure"), None)
    if name_node is None or proc_node is None:
        return
    block = next((c for c in proc_node.children if c.type == "block"), None)
    if block is None:
        return

    name = _text(name_node, source)
    params = _parameters(proc_node, source)
    owner_qn = resolve_owner(_receiver_name(params), package_qn, struct_index)
    if owner_qn is None:
        stem = Path(file).stem
        owner_qn = f"{package_qn}.{stem}" if package_qn != "__root__" else stem
        owner_name = stem
        receiver = ""
    else:
        owner_name = owner_qn.rsplit(".", 1)[-1]
        receiver = params[0].name if params else ""

    proc_rules = {r.name: r for r in extract_rules(decl, source)}
    owner_rules = class_rules.get(owner_qn, {})

    noinst = proc_rules.get(CTOR_RULE, owner_rules.get(CTOR_RULE))
    allow = literal_set(noinst.kwargs.get("allow", "")) if noinst is not None else None

    for constructed, line in _constructions(block, source):
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

    if IMMUTABLE_RULE in owner_rules and receiver:
        for field, line in _receiver_assignments(block, receiver, source):
            out.append(
                Finding(
                    rule=IMMUTABLE_RULE,
                    qualified_name=owner_qn,
                    message=(
                        f"'{owner_qn}' is tagged @cdec immutable but '{name}' "
                        f"reassigns field '{field}'."
                    ),
                    detail=f"{name}.{field}",
                    file=file,
                    line=line,
                )
            )


def _constructions(block: Node, source: bytes) -> list[tuple[str, int]]:
    """Types constructed in a procedure body, with their line numbers."""
    out: list[tuple[str, int]] = []
    stack = [block]
    while stack:
        node = stack.pop()
        stack.extend(node.children)
        line = node.start_point[0] + 1
        if node.type == "struct":
            # Composite literal `Money{...}`: the type is the leading identifier.
            ident = next((c for c in node.children if c.type == "identifier"), None)
            if ident is not None:
                out.append((_text(ident, source), line))
        elif node.type == "call_expression":
            callee = next((c for c in node.children if c.type == "identifier"), None)
            if callee is None or _text(callee, source) not in _ALLOCATORS:
                continue
            args = next((c for c in node.children if c.type == "argument_list"), None)
            first = args.named_children[0] if args and args.named_children else None
            if first is not None:
                out.append((_text(first, source).lstrip("^"), line))
    return out


def _receiver_assignments(
    block: Node, receiver: str, source: bytes
) -> list[tuple[str, int]]:
    """`recv.field = …` assignments inside the body."""
    out: list[tuple[str, int]] = []
    stack = [block]
    while stack:
        node = stack.pop()
        stack.extend(node.children)
        if node.type != "assignment_statement":
            continue
        target = node.named_children[0] if node.named_children else None
        if target is None or target.type != "member_expression":
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
