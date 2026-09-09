"""Parse a TypeScript project (a directory of .ts / .tsx files) into a
`code_constraints.core.Project`.

Uses `tree_sitter` with the `tree_sitter_typescript` grammar. Like the C# parser
this is a syntactic parse — there is no type-resolution across files, so an
inheritance / type reference that goes through an aliased import will appear as
the local alias rather than the source's qualified name.

Packages are derived from the directory layout (mirrors the Python parser);
file-level `namespace X { ... }` (TypeScript's `internal_module`) further nests
classes inside the directory-derived package.
"""

from __future__ import annotations

from pathlib import Path

import tree_sitter_typescript
from tree_sitter import Language, Node, Parser

from code_constraints.core.model import (
    Attribute,
    Class,
    ClassKind,
    Operation,
    Package,
    Parameter,
    Project,
    SourceLocation,
    Visibility,
)

_LANG_TS = Language(tree_sitter_typescript.language_typescript())
_LANG_TSX = Language(tree_sitter_typescript.language_tsx())
_PARSER_TS = Parser(_LANG_TS)
_PARSER_TSX = Parser(_LANG_TSX)

_SKIP_DIR_NAMES = {
    "node_modules", ".git", "dist", "build", "out", ".next", ".svelte-kit",
    ".turbo", ".cache", "coverage",
}

_TS_SUFFIXES = (".ts", ".tsx", ".mts", ".cts")


def parse_project(root: str | Path) -> Project:
    root_path = Path(root).resolve()
    if not root_path.is_dir():
        raise ValueError(f"not a directory: {root_path}")

    project = Project(source_language="typescript", root_path=str(root_path))
    package_index: dict[str, Package] = {}

    for ts_file in sorted(_iter_ts_files(root_path)):
        _parse_file(ts_file, root_path, project, package_index)

    return project


def _iter_ts_files(root_path: Path):
    for suf in _TS_SUFFIXES:
        for f in root_path.rglob(f"*{suf}"):
            if _should_skip(f):
                continue
            # Skip declaration files: they restate types defined elsewhere and
            # would double-count classes when parsed alongside their .ts pair.
            if f.name.endswith(".d.ts"):
                continue
            yield f


def _should_skip(p: Path) -> bool:
    return any(part in _SKIP_DIR_NAMES for part in p.parts)


def _parse_file(
    file: Path,
    root: Path,
    project: Project,
    package_index: dict[str, Package],
) -> None:
    source_bytes = file.read_bytes()
    parser = _PARSER_TSX if file.suffix == ".tsx" else _PARSER_TS
    tree = parser.parse(source_bytes)
    rel = file.relative_to(root)
    file_str = rel.as_posix()
    package_qn = _qualified_package_name(rel)
    _ensure_package(project, package_qn, package_index)

    parse_module_body(
        tree.root_node,
        source_bytes,
        package_qn=package_qn,
        project=project,
        package_index=package_index,
        file_str=file_str,
    )


def parse_module_body(
    root: Node,
    source: bytes,
    *,
    package_qn: str,
    project: Project,
    package_index: dict[str, Package],
    file_str: str,
) -> None:
    """Walk the top-level of a parsed TS source and ingest its declarations.

    Factored out of `_parse_file` so the Svelte parser can run it on the
    contents of a `<script>` block (which parse as a `program` with the same
    grammar) without re-implementing the dispatch logic.
    """
    for child in root.named_children:
        _visit_top_level(child, package_qn, project, package_index, source, file_str)


_CLASS_LIKE_TYPES = {
    "class_declaration",
    "abstract_class_declaration",
    "interface_declaration",
    "enum_declaration",
    "type_alias_declaration",
}


def _visit_top_level(
    node: Node,
    package_qn: str,
    project: Project,
    package_index: dict[str, Package],
    source: bytes,
    file_str: str,
) -> None:
    # Unwrap `export class ...` / `export default class ...`.
    if node.type == "export_statement":
        for c in node.named_children:
            _visit_top_level(c, package_qn, project, package_index, source, file_str)
        return

    # `expression_statement` shows up around `namespace X { ... }`.
    if node.type == "expression_statement" and node.named_child_count == 1:
        _visit_top_level(
            node.named_children[0], package_qn, project, package_index, source, file_str
        )
        return

    if node.type == "internal_module":
        _visit_namespace(node, package_qn, project, package_index, source, file_str)
        return

    if node.type in _CLASS_LIKE_TYPES:
        _ingest_class(node, package_qn, project, package_index, source, file_str)
        return


def _visit_namespace(
    node: Node,
    parent_qn: str,
    project: Project,
    package_index: dict[str, Package],
    source: bytes,
    file_str: str,
) -> None:
    # The name child is either `identifier` or `nested_identifier`
    # (`namespace Foo.Bar { ... }`).
    name_node = next(
        (c for c in node.named_children
         if c.type in ("identifier", "nested_identifier")),
        None,
    )
    name = _text(name_node, source) if name_node else "anon"
    qn = name if parent_qn in ("", "__root__") else f"{parent_qn}.{name}"
    _ensure_package(project, qn, package_index)

    body = next(
        (c for c in node.named_children if c.type == "statement_block"), None
    )
    if body is None:
        return
    for child in body.named_children:
        _visit_top_level(child, qn, project, package_index, source, file_str)


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


def _qualified_package_name(rel_file: Path) -> str:
    parts = list(rel_file.parts[:-1])
    if not parts:
        return "__root__"
    return ".".join(parts)


# ---------- class / member extraction ----------


def _ingest_class(
    node: Node,
    package_qn: str,
    project: Project,
    package_index: dict[str, Package],
    source: bytes,
    file_str: str,
) -> None:
    name_node = node.child_by_field_name("name") or _first_named_of_type(
        node, "type_identifier"
    )
    if name_node is None:
        return
    name = _text(name_node, source)
    qn = (
        f"{package_qn}.{name}"
        if package_qn and package_qn != "__root__"
        else name
    )

    cls = Class(
        name=name,
        qualified_name=qn,
        kind=_kind_for(node, source),
        bases=_bases(node, source),
        location=SourceLocation(
            file=file_str,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
        ),
        description=_jsdoc_for(node, source),
    )

    if node.type == "type_alias_declaration":
        # A type alias has no members; the `value` child is the aliased type
        # expression. We surface the alias text as a synthetic attribute so
        # the viewer shows what the alias resolves to.
        value = node.child_by_field_name("value")
        if value is not None:
            cls.attributes.append(
                Attribute(name="_alias", type=_text(value, source))
            )
    else:
        body = _class_body(node)
        if body is not None:
            for member in body.named_children:
                _ingest_member(member, cls, source)

    pkg = _ensure_package(project, package_qn, package_index)
    pkg.classes.append(cls)


def _class_body(node: Node) -> Node | None:
    for c in node.named_children:
        if c.type in ("class_body", "interface_body", "enum_body", "object_type"):
            return c
    return node.child_by_field_name("body")


def _kind_for(node: Node, source: bytes) -> ClassKind:
    if node.type == "interface_declaration":
        return "interface"
    if node.type == "enum_declaration":
        return "enum"
    if node.type == "type_alias_declaration":
        return "interface"  # closest UML equivalent — a named type contract
    if node.type == "abstract_class_declaration":
        return "abstract"
    return "class"


def _bases(node: Node, source: bytes) -> list[str]:
    """Collect `extends` + `implements` targets.

    Class heritage on `class_declaration` / `abstract_class_declaration` lives
    inside a `class_heritage` child holding `extends_clause` and/or
    `implements_clause`. Interfaces use an `extends_type_clause` directly on the
    `interface_declaration`.
    """
    out: list[str] = []
    for child in node.named_children:
        if child.type == "class_heritage":
            for sub in child.named_children:
                if sub.type == "extends_clause":
                    out.extend(_clause_types(sub, source))
                elif sub.type == "implements_clause":
                    out.extend(_clause_types(sub, source))
        elif child.type in ("extends_clause", "extends_type_clause", "implements_clause"):
            out.extend(_clause_types(child, source))
    return out


def _clause_types(clause: Node, source: bytes) -> list[str]:
    types: list[str] = []
    for c in clause.named_children:
        # Skip the `extends` / `implements` keyword token (unnamed).
        text = _text(c, source).strip()
        if text:
            types.append(text)
    return types


def _ingest_member(node: Node, cls: Class, source: bytes) -> None:
    t = node.type
    if t == "public_field_definition":
        cls.attributes.append(_attribute_from_field(node, source))
    elif t == "property_signature":
        cls.attributes.append(_attribute_from_property_sig(node, source))
    elif t in ("method_definition", "method_signature", "abstract_method_signature"):
        op = _operation_from_method(node, source)
        if op.name == "constructor":
            # TS allows `constructor(public name: string)` parameter properties.
            for p in op.parameters:
                # A parameter property is a constructor parameter that carried
                # an `accessibility_modifier` or `readonly` — encoded in the
                # parsed parameter via the leading marker in its name. We
                # capture this directly from the tree below.
                pass
            # Re-walk the formal parameters for parameter properties.
            params_node = node.child_by_field_name("parameters")
            if params_node is not None:
                for p in params_node.named_children:
                    attr = _attribute_from_parameter_property(p, source)
                    if attr is not None:
                        cls.attributes.append(attr)
        cls.operations.append(op)
    elif t == "enum_assignment" or t == "property_identifier":
        # Enum body entries are bare `property_identifier`s (no value) or
        # `enum_assignment` (with an initializer).
        if t == "property_identifier":
            cls.attributes.append(
                Attribute(
                    name=_text(node, source),
                    type=cls.name,
                    visibility=Visibility.PUBLIC,
                    is_static=True,
                )
            )
        else:
            name_node = node.child_by_field_name("name")
            value_node = node.child_by_field_name("value")
            if name_node is not None:
                cls.attributes.append(
                    Attribute(
                        name=_text(name_node, source),
                        type=cls.name,
                        visibility=Visibility.PUBLIC,
                        is_static=True,
                        default=_text(value_node, source) if value_node else None,
                    )
                )


def _attribute_from_field(node: Node, source: bytes) -> Attribute:
    name_node = node.child_by_field_name("name") or _first_named_of_type(
        node, "property_identifier"
    )
    name = _text(name_node, source) if name_node else ""
    type_node = _first_named_of_type(node, "type_annotation")
    type_text = _strip_type_annotation(_text(type_node, source)) if type_node else ""
    value_node = node.child_by_field_name("value")
    default = _text(value_node, source) if value_node else None

    vis = _visibility_for_member(node, name, source)
    is_static = _has_keyword(node, "static")
    is_readonly = _has_keyword(node, "readonly")
    return Attribute(
        name=name,
        type=type_text,
        visibility=vis,
        is_static=is_static,
        is_readonly=is_readonly,
        default=default,
    )


def _attribute_from_property_sig(node: Node, source: bytes) -> Attribute:
    name_node = node.child_by_field_name("name") or _first_named_of_type(
        node, "property_identifier"
    )
    name = _text(name_node, source) if name_node else ""
    type_node = _first_named_of_type(node, "type_annotation")
    type_text = _strip_type_annotation(_text(type_node, source)) if type_node else ""
    return Attribute(
        name=name,
        type=type_text,
        visibility=_visibility_for_member(node, name, source),
        is_readonly=_has_keyword(node, "readonly"),
    )


def _attribute_from_parameter_property(param: Node, source: bytes) -> Attribute | None:
    """Capture `constructor(public name: string)` parameter properties.

    Such parameters carry an `accessibility_modifier` or `readonly` keyword;
    everything else is a plain parameter we should NOT mirror as an attribute.
    """
    has_marker = False
    for c in param.children:
        if c.type == "accessibility_modifier":
            has_marker = True
        if c.type == "readonly":
            has_marker = True
    if not has_marker:
        return None
    if param.type not in ("required_parameter", "optional_parameter"):
        return None
    name_node = next(
        (c for c in param.named_children if c.type in ("identifier", "shorthand_property_identifier_pattern")),
        None,
    )
    name = _text(name_node, source) if name_node else ""
    type_node = _first_named_of_type(param, "type_annotation")
    type_text = _strip_type_annotation(_text(type_node, source)) if type_node else ""
    return Attribute(
        name=name,
        type=type_text,
        visibility=_visibility_for_member(param, name, source),
        is_readonly=_has_keyword(param, "readonly"),
    )


def _operation_from_method(node: Node, source: bytes) -> Operation:
    name_node = node.child_by_field_name("name") or _first_named_of_type(
        node, "property_identifier"
    )
    name = _text(name_node, source) if name_node else ""
    return_node = _first_named_of_type(node, "type_annotation")
    return_type = (
        _strip_type_annotation(_text(return_node, source)) if return_node else ""
    )

    params: list[Parameter] = []
    params_node = node.child_by_field_name("parameters")
    if params_node is not None:
        for p in params_node.named_children:
            if p.type not in ("required_parameter", "optional_parameter"):
                continue
            params.append(_parameter_from(p, source))

    return Operation(
        name=name,
        parameters=params,
        return_type=return_type,
        visibility=_visibility_for_member(node, name, source),
        is_static=_has_keyword(node, "static"),
        is_abstract=node.type == "abstract_method_signature" or _has_keyword(node, "abstract"),
        description=_jsdoc_for(node, source),
    )


def _parameter_from(p: Node, source: bytes) -> Parameter:
    name_node = next(
        (c for c in p.named_children
         if c.type in ("identifier", "shorthand_property_identifier_pattern",
                       "object_pattern", "array_pattern")),
        None,
    )
    name = _text(name_node, source) if name_node else ""
    type_node = _first_named_of_type(p, "type_annotation")
    type_text = _strip_type_annotation(_text(type_node, source)) if type_node else ""
    # Default value is the named child after the type annotation.
    default = None
    saw_type = type_node is None
    for c in p.named_children:
        if c is type_node:
            saw_type = True
            continue
        if c is name_node:
            continue
        if saw_type and c.type not in ("type_annotation", "accessibility_modifier"):
            default = _text(c, source)
            break
    return Parameter(name=name, type=type_text, default=default)


# ---------- modifier helpers ----------


def _visibility_for_member(node: Node, name: str, source: bytes) -> Visibility:
    for c in node.children:
        if c.type == "accessibility_modifier":
            text = _text(c, source).strip()
            if text == "private":
                return Visibility.PRIVATE
            if text == "protected":
                return Visibility.PROTECTED
            if text == "public":
                return Visibility.PUBLIC
    # TS convention: leading `#` is a private field; leading `_` is "by
    # convention" protected.
    if name.startswith("#"):
        return Visibility.PRIVATE
    if name.startswith("_"):
        return Visibility.PROTECTED
    return Visibility.PUBLIC


def _has_keyword(node: Node, keyword: str) -> bool:
    """True if `node` has a direct (unnamed or named) child whose token text
    matches `keyword`."""
    for c in node.children:
        if c.type == keyword:
            return True
    return False


# ---------- text helpers ----------


def _text(node: Node | None, source: bytes) -> str:
    if node is None:
        return ""
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _strip_type_annotation(text: str) -> str:
    """Turn `: Foo<Bar>` into `Foo<Bar>` and trim whitespace."""
    text = text.strip()
    if text.startswith(":"):
        text = text[1:].strip()
    return text


def _first_named_of_type(node: Node, type_name: str) -> Node | None:
    for c in node.named_children:
        if c.type == type_name:
            return c
    return None


def _jsdoc_for(node: Node, source: bytes) -> str | None:
    """Read a `/** ... */` JSDoc block immediately above `node`.

    Class / interface declarations are commonly wrapped in an
    `export_statement` whose own `prev_sibling` is the comment we want, so we
    step up to the export wrapper when the immediate previous sibling is the
    `export` keyword.
    """
    start = node
    if (
        node.parent is not None
        and node.parent.type == "export_statement"
        and node.prev_sibling is not None
        and node.prev_sibling.type == "export"
    ):
        start = node.parent

    sib = start.prev_sibling
    # Skip past unnamed token siblings (semicolons, keywords) to find the
    # nearest comment OR named declaration. We only accept the comment if we
    # encounter it before any other declaration.
    while sib is not None and sib.type != "comment" and not sib.is_named:
        sib = sib.prev_sibling
    if sib is None or sib.type != "comment":
        return None
    raw = _text(sib, source).strip()
    if not raw.startswith("/**"):
        return None
    # Strip /** ... */ and per-line " * " prefixes.
    body = raw[3:]
    if body.endswith("*/"):
        body = body[:-2]
    lines = []
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("*"):
            stripped = stripped[1:].strip()
        if stripped.startswith("@"):
            break  # stop at first @param/@returns tag
        lines.append(stripped)
    joined = " ".join(s for s in lines if s)
    return joined or None
