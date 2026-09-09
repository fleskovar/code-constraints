"""Parse an Odin project (directory of .odin files) into a `code_constraints.core.Project`.

Uses `tree_sitter` with the `tree_sitter_odin` grammar. Like the C# and
TypeScript parsers this is a syntactic parse — there is no semantic resolution,
so a type reference through an import alias appears as the alias.

Two mapping decisions worth knowing, both forced by Odin having no classes:

**Procedures become operations of their receiver.** Odin declares procedures at
package scope, so `scale :: proc(v: ^Vec, k: f64)` is modelled as the operation
`scale` on `Vec` — the receiver is the first parameter, with `^`/`[]`/`[dynamic]`
wrappers stripped. This is what makes `//@cdec locked` on a procedure constrain
the method a reader would expect. Because a procedure can be declared in a
different file from its struct, the walk is **two-phase**: every file is parsed
and its structs registered first, then procedures are attached.

**Free procedures become a `static` class.** A procedure whose first parameter
isn't a project struct has no receiver, so it lands on a synthetic class named
after its file stem with `kind="static"` — the UML utility-class idiom. Without
this, a tag on a free procedure would be silently dropped.

Odin's other subtype mechanism, struct embedding (`using base: Base`), maps to
`bases`, so embedded structs draw as inheritance.
"""

from __future__ import annotations

from pathlib import Path

import tree_sitter_odin
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
from code_constraints.odin.rules_extract import extract_rules

_LANG = Language(tree_sitter_odin.language())
_PARSER = Parser(_LANG)

_SKIP_DIR_NAMES = {".git", "build", "bin", "out", ".cdec_cache"}

_TYPE_DECL_TYPES = {
    "struct_declaration": "struct",
    "enum_declaration": "enum",
    "union_declaration": "class",
    "bit_field_declaration": "struct",
}

# Type wrappers stripped when resolving a parameter type to a receiver struct.
_TYPE_PREFIXES = ("^", "[dynamic]", "[]", "*")


def parse_project(root: str | Path) -> Project:
    root_path = Path(root).resolve()
    if not root_path.is_dir():
        raise ValueError(f"not a directory: {root_path}")

    project = Project(source_language="odin", root_path=str(root_path))
    package_index: dict[str, Package] = {}
    # (package_qn, struct name) -> Class, for receiver resolution in phase 2.
    class_index: dict[tuple[str, str], Class] = {}
    pending: list[_PendingProc] = []

    for odin_file in sorted(root_path.rglob("*.odin")):
        if _should_skip(odin_file):
            continue
        _parse_file(odin_file, root_path, project, package_index, class_index, pending)

    _attach_procedures(pending, project, package_index, class_index)
    return project


def _should_skip(p: Path) -> bool:
    if p.name in SHIM_FILENAMES:
        return True
    return any(part in _SKIP_DIR_NAMES for part in p.parts)


class _PendingProc:
    """A parsed procedure awaiting receiver resolution in phase 2."""

    __slots__ = ("node", "source", "package_qn", "file", "stem")

    def __init__(self, node: Node, source: bytes, package_qn: str, file: str, stem: str):
        self.node = node
        self.source = source
        self.package_qn = package_qn
        self.file = file
        self.stem = stem


def _parse_file(
    file: Path,
    root: Path,
    project: Project,
    package_index: dict[str, Package],
    class_index: dict[tuple[str, str], Class],
    pending: list[_PendingProc],
) -> None:
    source = file.read_bytes()
    tree = _PARSER.parse(source)
    rel = file.relative_to(root)
    file_str = rel.as_posix()
    package_qn = _package_name(tree.root_node, source, rel)
    _ensure_package(project, package_qn, package_index)

    for child in tree.root_node.named_children:
        if child.type in _TYPE_DECL_TYPES:
            cls = _ingest_type(child, package_qn, source, file_str)
            if cls is None:
                continue
            pkg = _ensure_package(project, package_qn, package_index)
            pkg.classes.append(cls)
            class_index[(package_qn, cls.name)] = cls
        elif child.type == "procedure_declaration":
            pending.append(_PendingProc(child, source, package_qn, file_str, rel.stem))


def _package_name(root: Node, source: bytes, rel: Path) -> str:
    """Package qualified name: the directory path, or the declared `package`
    name for files at the project root.

    Odin already scopes one package per directory, so the directory path gives
    the same grouping with the nesting the package diagram wants.
    """
    parts = list(rel.parts[:-1])
    if parts:
        return ".".join(parts)
    for child in root.named_children:
        if child.type == "package_declaration":
            ident = next((c for c in child.children if c.type == "identifier"), None)
            if ident is not None:
                return _text(ident, source)
    return "__root__"


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


# ---------- type declarations ----------

def _ingest_type(node: Node, package_qn: str, source: bytes, file_str: str) -> Class | None:
    name_node = next((c for c in node.children if c.type == "identifier"), None)
    if name_node is None:
        return None
    name = _text(name_node, source)
    qn = f"{package_qn}.{name}" if package_qn != "__root__" else name

    cls = Class(
        name=name,
        qualified_name=qn,
        kind=_TYPE_DECL_TYPES[node.type],  # type: ignore[arg-type]
        location=SourceLocation(
            file=file_str,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
        ),
        rules=extract_rules(node, source),
    )

    if node.type == "enum_declaration":
        _ingest_enum_members(node, cls, source)
    elif node.type == "union_declaration":
        _ingest_union_variants(node, cls, source)
    else:
        _ingest_fields(node, cls, source)

    cls.dependencies = _dedupe(cls.dependencies, drop=cls.name)
    return cls


def _ingest_fields(node: Node, cls: Class, source: bytes) -> None:
    for field in node.named_children:
        if field.type != "field":
            continue
        type_node = next((c for c in field.children if c.type == "type"), None)
        type_text = _text(type_node, source) if type_node else ""
        embedded = any(c.type == "using" or _text(c, source) == "using" for c in field.children)
        names = [
            _text(c, source)
            for c in field.children
            if c.type == "identifier"
        ]
        if embedded:
            # `using base: Base` is Odin's subtype embedding — model it as
            # inheritance rather than as a plain field.
            if type_text:
                cls.bases.append(_base_name(type_text))
            continue
        for field_name in names:
            cls.attributes.append(
                Attribute(
                    name=field_name,
                    type=type_text,
                    visibility=Visibility.PUBLIC,
                )
            )
        if type_text:
            cls.dependencies.append(_strip_wrappers(type_text))


def _ingest_enum_members(node: Node, cls: Class, source: bytes) -> None:
    started = False
    for child in node.children:
        if child.type == "{":
            started = True
            continue
        if not started or child.type == "}":
            continue
        if child.type == "identifier":
            cls.attributes.append(
                Attribute(
                    name=_text(child, source),
                    type=cls.name,
                    visibility=Visibility.PUBLIC,
                    is_static=True,
                    is_readonly=True,
                )
            )


def _ingest_union_variants(node: Node, cls: Class, source: bytes) -> None:
    for child in node.named_children:
        if child.type != "type":
            continue
        variant = _text(child, source)
        cls.attributes.append(
            Attribute(
                name=variant,
                type=variant,
                visibility=Visibility.PUBLIC,
                is_static=True,
                is_readonly=True,
            )
        )
        cls.dependencies.append(_strip_wrappers(variant))


# ---------- procedures ----------

def _attach_procedures(
    pending: list[_PendingProc],
    project: Project,
    package_index: dict[str, Package],
    class_index: dict[tuple[str, str], Class],
) -> None:
    """Phase 2: attach each procedure to its receiver struct, or to the file's
    synthetic module class."""
    module_classes: dict[tuple[str, str], Class] = {}

    for proc in pending:
        name_node = next((c for c in proc.node.children if c.type == "identifier"), None)
        proc_node = next((c for c in proc.node.children if c.type == "procedure"), None)
        if name_node is None or proc_node is None:
            continue

        params = _parameters(proc_node, proc.source)
        owner = _receiver(params, proc.package_qn, class_index)
        operation = Operation(
            name=_text(name_node, proc.source),
            # The receiver is `self` in UML terms, so drop it from the signature.
            parameters=params[1:] if owner is not None else params,
            return_type=_return_type(proc_node, proc.source),
            visibility=_visibility(proc.node, proc.source),
            is_static=owner is None,
            rules=extract_rules(proc.node, proc.source),
        )

        if owner is None:
            owner = _module_class(proc, project, package_index, module_classes)
        owner.operations.append(operation)
        owner.dependencies.extend(_body_type_refs(proc_node, proc.source))
        owner.dependencies = _dedupe(owner.dependencies, drop=owner.name)


def _module_class(
    proc: _PendingProc,
    project: Project,
    package_index: dict[str, Package],
    module_classes: dict[tuple[str, str], Class],
) -> Class:
    """The synthetic `static` class collecting a file's receiver-less procedures."""
    key = (proc.package_qn, proc.stem)
    existing = module_classes.get(key)
    if existing is not None:
        return existing
    qn = f"{proc.package_qn}.{proc.stem}" if proc.package_qn != "__root__" else proc.stem
    cls = Class(
        name=proc.stem,
        qualified_name=qn,
        kind="static",
        location=SourceLocation(file=proc.file, start_line=1, end_line=1),
        description=f"Package-scope procedures declared in {proc.file}.",
    )
    _ensure_package(project, proc.package_qn, package_index).classes.append(cls)
    module_classes[key] = cls
    return cls


def _receiver(
    params: list[Parameter],
    package_qn: str,
    class_index: dict[tuple[str, str], Class],
) -> Class | None:
    """The struct a procedure's first parameter names, if any.

    Same-package first (Odin's normal case), then any package — an unqualified
    match across packages is the best a syntactic parse can do, and mirrors the
    C# parser's documented lack of type resolution.
    """
    base = _receiver_name(params)
    if not base:
        return None
    same_package = class_index.get((package_qn, base))
    if same_package is not None:
        return same_package
    matches = [cls for (_pkg, name), cls in class_index.items() if name == base]
    return matches[0] if len(matches) == 1 else None


def _receiver_name(params: list[Parameter]) -> str:
    """Bare type name of a procedure's first parameter — its receiver candidate.

    Shared with `odin.fingerprint` so lock target names resolve to exactly the
    same owner the model shows.
    """
    if not params:
        return ""
    base = _strip_wrappers(params[0].type)
    return base.rsplit(".", 1)[-1] if base else ""


def _parameters(proc_node: Node, source: bytes) -> list[Parameter]:
    params_node = next((c for c in proc_node.children if c.type == "parameters"), None)
    if params_node is None:
        return []
    out: list[Parameter] = []
    for param in params_node.named_children:
        if param.type != "parameter":
            continue
        names = [c for c in param.children if c.type == "identifier"]
        type_node = next((c for c in param.children if c.type == "type"), None)
        default = _default_value(param, source)
        type_text = _text(type_node, source) if type_node else ""
        if not names:
            # `proc(^Vec)` — an unnamed parameter is still positionally typed.
            out.append(Parameter(name="", type=type_text, default=default))
            continue
        for name_node in names:
            out.append(
                Parameter(name=_text(name_node, source), type=type_text, default=default)
            )
    return out


def _default_value(param: Node, source: bytes) -> str | None:
    for i, child in enumerate(param.children):
        if child.type == "=" or _text(child, source) == "=":
            value = next((c for c in param.children[i + 1 :] if c.is_named), None)
            return _text(value, source) if value is not None else None
    return None


def _return_type(proc_node: Node, source: bytes) -> str:
    """The declared result type. Odin puts it in a `type` child after `->`, so
    it is distinguished from parameter types by position, not by field name."""
    seen_arrow = False
    for child in proc_node.children:
        if child.type == "->" or _text(child, source) == "->":
            seen_arrow = True
            continue
        if seen_arrow and child.type == "type":
            return _text(child, source)
    return ""


def _visibility(decl: Node, source: bytes) -> Visibility:
    attrs = next((c for c in decl.children if c.type == "attributes"), None)
    if attrs is not None and "private" in _text(attrs, source):
        return Visibility.PRIVATE
    return Visibility.PUBLIC


def _body_type_refs(proc_node: Node, source: bytes) -> list[str]:
    """Capitalised identifiers used inside a procedure body — candidate type
    references for association edges.

    Heuristic, like the C# parser: `resolve_association` keeps only the ones that
    match a project class, so locals and builtins drop out. Only the block is
    walked, so parameter names and the `//@cdec` comments above never leak in.
    """
    block = next((c for c in proc_node.children if c.type == "block"), None)
    if block is None:
        return []
    out: list[str] = []
    seen: set[str] = set()
    stack = [block]
    while stack:
        node = stack.pop()
        stack.extend(node.children)
        if node.type != "identifier":
            continue
        text = _text(node, source)
        if text and text[0].isupper() and text not in seen:
            seen.add(text)
            out.append(text)
    return out


# ---------- helpers ----------

def _strip_wrappers(type_text: str) -> str:
    """Reduce `^Vec` / `[dynamic]Vec` / `[]Vec` to `Vec`."""
    text = type_text.strip()
    changed = True
    while changed:
        changed = False
        for prefix in _TYPE_PREFIXES:
            if text.startswith(prefix):
                text = text[len(prefix) :].strip()
                changed = True
    return text


def _base_name(type_text: str) -> str:
    return _strip_wrappers(type_text).rsplit(".", 1)[-1]


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
