"""Parse a Julia project (directory of .jl files) into a `code_constraints.core.Project`.

Uses `tree_sitter` with the `tree_sitter_julia` grammar. Syntactic only — there
is no method-table or type resolution, so a type written through an alias
appears as the alias.

Julia has types but no methods-inside-types, so the mapping mirrors the Odin
parser's:

**Functions become operations of their first argument's type.** `settle(inv::Invoice,
rate)` is modelled as the operation `settle` on `Invoice`. That is what makes
`@locked function settle(inv::Invoice)` constrain the method a reader expects,
and it is the honest reading of single-argument dispatch. Because a function can
be defined in a different file from its struct, the walk is **two-phase**: all
type definitions are registered first, then functions are attached.

**Functions with no struct-typed first argument become a `static` class** named
after the enclosing module (or the file stem), the UML utility-class idiom —
without it, a tag on a free function would be silently dropped.

Packages come from the directory layout, with each `module X ... end` nesting
further inside it — the same scheme the TypeScript parser uses for `namespace`.

Inner constructors (`Invoice(id) = new(id, 0.0)` inside the struct body) are
ingested as operations of their own struct, so a `@locked` inner constructor is
lockable like any other member.
"""

from __future__ import annotations

from pathlib import Path

import tree_sitter_julia
from tree_sitter import Language, Node, Parser

from code_constraints.core.model import (
    Attribute,
    Class,
    ClassKind,
    Operation,
    Package,
    Parameter,
    RuleAnnotation,
    Project,
    SourceLocation,
    Visibility,
)
from code_constraints.core.rules import SHIM_FILENAMES
from code_constraints.julia.rules_extract import unwrap_macros, using_has_shim

_LANG = Language(tree_sitter_julia.language())
_PARSER = Parser(_LANG)

_SKIP_DIR_NAMES = {".git", "docs", "deps", ".julia", "build", ".cdec_cache"}

_TYPE_DEFINITION_TYPES = {
    "struct_definition": "struct",
    "abstract_definition": "abstract",
    "primitive_definition": "struct",
}


def parse_project(root: str | Path) -> Project:
    root_path = Path(root).resolve()
    if not root_path.is_dir():
        raise ValueError(f"not a directory: {root_path}")

    project = Project(source_language="julia", root_path=str(root_path))
    package_index: dict[str, Package] = {}
    class_index: dict[tuple[str, str], Class] = {}
    pending: list[_PendingFunc] = []

    for jl_file in sorted(root_path.rglob("*.jl")):
        if _should_skip(jl_file):
            continue
        _parse_file(jl_file, root_path, project, package_index, class_index, pending)

    _attach_functions(pending, project, package_index, class_index)
    return project


def _should_skip(p: Path) -> bool:
    if p.name in SHIM_FILENAMES:
        return True
    return any(part in _SKIP_DIR_NAMES for part in p.parts)


class _PendingFunc:
    """A parsed function awaiting receiver resolution in phase 2."""

    __slots__ = ("node", "rules", "source", "package_qn", "file", "scope")

    def __init__(
        self,
        node: Node,
        rules: list[RuleAnnotation],
        source: bytes,
        package_qn: str,
        file: str,
        scope: str,
    ):
        self.node = node
        self.rules = rules
        self.source = source
        self.package_qn = package_qn
        self.file = file
        self.scope = scope


def _parse_file(
    file: Path,
    root: Path,
    project: Project,
    package_index: dict[str, Package],
    class_index: dict[tuple[str, str], Class],
    pending: list[_PendingFunc],
) -> None:
    source = file.read_bytes()
    tree = _PARSER.parse(source)
    rel = file.relative_to(root)
    file_str = rel.as_posix()
    package_qn = _qualified_package_name(rel)
    shim = using_has_shim(tree.root_node, source)
    _ensure_package(project, package_qn, package_index)

    _visit_block(
        tree.root_node,
        package_qn,
        rel.stem,
        project,
        package_index,
        class_index,
        pending,
        source,
        file_str,
        shim,
    )


def _visit_block(
    parent: Node,
    package_qn: str,
    scope: str,
    project: Project,
    package_index: dict[str, Package],
    class_index: dict[tuple[str, str], Class],
    pending: list[_PendingFunc],
    source: bytes,
    file_str: str,
    shim: bool,
) -> None:
    for child in parent.named_children:
        rules, node = unwrap_macros(child, source, shim)
        if node is None:
            continue

        if node.type == "module_definition":
            name = _module_name(node, source)
            nested = f"{package_qn}.{name}" if package_qn != "__root__" else name
            _ensure_package(project, nested, package_index)
            # `scope` stays the file stem, so receiver-less functions from every
            # module in one file share one `static` class — matching how the Odin
            # and Lua parsers name theirs, and avoiding a `Billing.Billing` clash
            # when the module and its package segment have the same name.
            _visit_block(
                node, nested, scope, project, package_index, class_index,
                pending, source, file_str, shim,
            )
        elif node.type in _TYPE_DEFINITION_TYPES:
            cls = _ingest_type(node, rules, package_qn, source, file_str)
            if cls is None:
                continue
            _ensure_package(project, package_qn, package_index).classes.append(cls)
            class_index[(package_qn, cls.name)] = cls
        elif node.type == "function_definition" or _is_short_function(node):
            pending.append(
                _PendingFunc(node, rules, source, package_qn, file_str, scope)
            )


def _module_name(node: Node, source: bytes) -> str:
    ident = next((c for c in node.children if c.type == "identifier"), None)
    return _text(ident, source) if ident is not None else "anon"


def _is_short_function(node: Node) -> bool:
    """`f(x::T) = ...` — an assignment whose left side is a call."""
    if node.type != "assignment":
        return False
    first = node.named_children[0] if node.named_children else None
    return first is not None and first.type == "call_expression"


# ---------- type definitions ----------

def _ingest_type(
    node: Node,
    rules: list[RuleAnnotation],
    package_qn: str,
    source: bytes,
    file_str: str,
) -> Class | None:
    head = next((c for c in node.children if c.type == "type_head"), None)
    if head is None:
        return None
    name, bases = _type_head_parts(head, source)
    if not name:
        return None
    qn = f"{package_qn}.{name}" if package_qn != "__root__" else name

    cls = Class(
        name=name,
        qualified_name=qn,
        kind=_kind_for(node),
        bases=bases,
        location=SourceLocation(
            file=file_str,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
        ),
        rules=rules,
    )

    for member in node.named_children:
        if member is head:
            continue
        if member.type == "typed_expression":
            field, type_text = _typed_parts(member, source)
            if field:
                cls.attributes.append(
                    Attribute(
                        name=field,
                        type=type_text,
                        visibility=_visibility(field),
                        # A non-`mutable struct` is immutable in Julia, so its
                        # fields genuinely are read-only.
                        is_readonly=not _is_mutable(node),
                    )
                )
                cls.dependencies.append(_base_name(type_text))
        elif member.type == "identifier":
            cls.attributes.append(
                Attribute(
                    name=_text(member, source),
                    visibility=_visibility(_text(member, source)),
                    is_readonly=not _is_mutable(node),
                )
            )
        elif member.type == "function_definition" or _is_short_function(member):
            # Inner constructor.
            inner_rules, inner = unwrap_macros(member, source, False)
            operation = _operation(inner or member, inner_rules, source)
            if operation is not None:
                cls.operations.append(operation)

    cls.dependencies = _dedupe(cls.dependencies, drop=cls.name)
    return cls


def _kind_for(node: Node) -> ClassKind:
    if node.type == "abstract_definition":
        return "abstract"
    return "struct"


def _is_mutable(node: Node) -> bool:
    return any(c.type == "mutable" or c.text == b"mutable" for c in node.children)


def _type_head_parts(head: Node, source: bytes) -> tuple[str, list[str]]:
    """`Invoice <: AbstractInvoice` -> ("Invoice", ["AbstractInvoice"])."""
    inner = head.named_children[0] if head.named_children else None
    if inner is None:
        return _text(head, source), []
    if inner.type == "binary_expression":
        parts = [c for c in inner.named_children if c.type != "operator"]
        if len(parts) >= 2:
            return _bare_type_name(parts[0], source), [_bare_type_name(parts[-1], source)]
    return _bare_type_name(inner, source), []


def _bare_type_name(node: Node, source: bytes) -> str:
    """Drop type parameters: `Draft{T}` -> `Draft`."""
    if node.type == "parametrized_type_expression":
        ident = node.named_children[0] if node.named_children else None
        return _text(ident, source) if ident is not None else ""
    return _text(node, source)


def _typed_parts(node: Node, source: bytes) -> tuple[str, str]:
    """`id::String` -> ("id", "String")."""
    named = node.named_children
    if len(named) < 2:
        return _text(node, source), ""
    return _text(named[0], source), _text(named[-1], source)


# ---------- functions ----------

def _attach_functions(
    pending: list[_PendingFunc],
    project: Project,
    package_index: dict[str, Package],
    class_index: dict[tuple[str, str], Class],
) -> None:
    module_classes: dict[tuple[str, str], Class] = {}

    for func in pending:
        operation = _operation(func.node, func.rules, func.source)
        if operation is None:
            continue
        owner = _receiver(operation.parameters, func.package_qn, class_index)
        if owner is not None:
            # The receiver is `self` in UML terms; drop it from the signature.
            operation.parameters = operation.parameters[1:]
        else:
            operation.is_static = True
            owner = _module_class(func, project, package_index, module_classes)
        owner.operations.append(operation)
        owner.dependencies.extend(_body_type_refs(func.node, func.source))
        owner.dependencies = _dedupe(owner.dependencies, drop=owner.name)


def _module_class(
    func: _PendingFunc,
    project: Project,
    package_index: dict[str, Package],
    module_classes: dict[tuple[str, str], Class],
) -> Class:
    key = (func.package_qn, func.scope)
    existing = module_classes.get(key)
    if existing is not None:
        return existing
    qn = (
        f"{func.package_qn}.{func.scope}"
        if func.package_qn != "__root__"
        else func.scope
    )
    cls = Class(
        name=func.scope,
        qualified_name=qn,
        kind="static",
        location=SourceLocation(file=func.file, start_line=1, end_line=1),
        description=f"Functions with no struct receiver, declared in {func.file}.",
    )
    _ensure_package(project, func.package_qn, package_index).classes.append(cls)
    module_classes[key] = cls
    return cls


def _receiver(
    params: list[Parameter],
    package_qn: str,
    class_index: dict[tuple[str, str], Class],
) -> Class | None:
    """The struct a function's first argument is annotated with, if any."""
    if not params or not params[0].type:
        return None
    base = _base_name(params[0].type)
    if not base:
        return None
    same_package = class_index.get((package_qn, base))
    if same_package is not None:
        return same_package
    matches = [cls for (_pkg, name), cls in class_index.items() if name == base]
    return matches[0] if len(matches) == 1 else None


def _operation(node: Node, rules: list[RuleAnnotation], source: bytes) -> Operation | None:
    call, return_type = _signature_parts(node, source)
    if call is None:
        return None
    name_node = call.named_children[0] if call.named_children else None
    if name_node is None:
        return None
    return Operation(
        name=_text(name_node, source),
        parameters=_parameters(call, source),
        return_type=return_type,
        visibility=Visibility.PUBLIC,
        rules=rules,
    )


def _signature_parts(node: Node, source: bytes) -> tuple[Node | None, str]:
    """Locate the `call_expression` naming the function, plus its return type.

    Long form nests it under `signature` (optionally through a `where_expression`
    for type parameters and a `typed_expression` for the `::Ret` annotation);
    short form puts it directly on the assignment's left.
    """
    if node.type == "assignment":
        first = node.named_children[0] if node.named_children else None
        return (first if first is not None and first.type == "call_expression" else None), ""

    signature = next((c for c in node.children if c.type == "signature"), None)
    if signature is None:
        return None, ""
    current = signature.named_children[0] if signature.named_children else None
    return_type = ""
    while current is not None:
        if current.type == "call_expression":
            return current, return_type
        if current.type == "typed_expression":
            named = current.named_children
            if len(named) >= 2:
                return_type = _text(named[-1], source)
            current = named[0] if named else None
            continue
        if current.type == "where_expression":
            current = current.named_children[0] if current.named_children else None
            continue
        break
    return None, return_type


def _parameters(call: Node, source: bytes) -> list[Parameter]:
    arglist = next((c for c in call.children if c.type == "argument_list"), None)
    if arglist is None:
        return []
    out: list[Parameter] = []
    for arg in arglist.named_children:
        if arg.type == "identifier":
            out.append(Parameter(name=_text(arg, source)))
        elif arg.type == "typed_expression":
            name, type_text = _typed_parts(arg, source)
            out.append(Parameter(name=name, type=type_text))
        elif arg.type == "named_argument":
            named = arg.named_children
            target = named[0] if named else None
            default = _text(named[-1], source) if len(named) >= 2 else None
            if target is not None and target.type == "typed_expression":
                name, type_text = _typed_parts(target, source)
            else:
                name, type_text = _text(target, source), ""
            out.append(Parameter(name=name, type=type_text, default=default))
        elif arg.type == "splat_expression":
            inner = arg.named_children[0] if arg.named_children else None
            out.append(Parameter(name=f"{_text(inner, source)}..."))
    return out


def _body_type_refs(node: Node, source: bytes) -> list[str]:
    """Capitalised identifiers in a function body — candidate type references.

    In Julia a constructor call is just a call on the type name, so this also
    catches `Money(1)`. `resolve_association` keeps only project classes.
    """
    out: list[str] = []
    seen: set[str] = set()
    signature = next((c for c in node.children if c.type == "signature"), None)
    for child in node.named_children:
        if child is signature:
            continue
        stack = [child]
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
    return Visibility.PRIVATE if name.startswith("_") else Visibility.PUBLIC


def _base_name(type_text: str) -> str:
    """Reduce `Vector{Invoice}` / `Main.Invoice` to a bare name."""
    text = type_text.strip().lstrip("^")
    if "{" in text:
        text = text.split("{", 1)[0]
    return text.rsplit(".", 1)[-1].strip()


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
