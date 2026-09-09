"""Parse a C# project (directory of .cs files) into a `code_constraints.core.Project`.

Uses `tree_sitter` with the `tree_sitter_c_sharp` grammar. This is a syntactic
parse only — there is no semantic / type resolution, so inheritance lines may
appear as their textual form rather than as fully qualified names. That is a
documented limitation accepted for v1.
"""

from __future__ import annotations

import re
from pathlib import Path

import tree_sitter_c_sharp
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
from code_constraints.core.tags import find_tags
from code_constraints.csharp.activity import build_activity_from_tag
from code_constraints.csharp.rules_extract import extract_rules, using_has_shim
from code_constraints.csharp.sequence import build_sequence_from_tag

_LANG = Language(tree_sitter_c_sharp.language())
_PARSER = Parser(_LANG)


def parse_project(root: str | Path) -> Project:
    root_path = Path(root).resolve()
    if not root_path.is_dir():
        raise ValueError(f"not a directory: {root_path}")

    project = Project(source_language="csharp", root_path=str(root_path))
    package_index: dict[str, Package] = {}

    for cs_file in sorted(root_path.rglob("*.cs")):
        if _should_skip(cs_file):
            continue
        _parse_file(cs_file, root_path, project, package_index)

    return project


_SKIP_DIR_NAMES = {"bin", "obj", ".git", "packages", "TestResults"}


def _should_skip(p: Path) -> bool:
    return any(part in _SKIP_DIR_NAMES for part in p.parts)


def _parse_file(
    file: Path,
    root: Path,
    project: Project,
    package_index: dict[str, Package],
) -> None:
    source_bytes = file.read_bytes()
    tree = _PARSER.parse(source_bytes)
    file_str = str(file.relative_to(root).as_posix())
    source_text = source_bytes.decode("utf-8", errors="replace")

    # Find every namespace_declaration (including file-scoped) and class-like
    # declarations directly inside the file (which may belong to an implicit
    # global namespace).
    cu = tree.root_node
    shim_in_scope = using_has_shim(cu, source_bytes)
    # File-scoped namespace claims every subsequent top-level declaration.
    file_scoped_ns: str | None = None
    for child in cu.named_children:
        if child.type == "namespace_declaration":
            _visit_namespace(
                child, "", project, package_index, source_bytes, file_str, shim_in_scope
            )
        elif child.type == "file_scoped_namespace_declaration":
            name_node = child.child_by_field_name("name")
            file_scoped_ns = (
                _text(name_node, source_bytes) if name_node else "anon"
            )
            _ensure_package(project, file_scoped_ns, package_index)
        elif child.type in _CLASS_LIKE_TYPES:
            target_ns = file_scoped_ns or "__root__"
            _ingest_class(
                child, target_ns, project, package_index, source_bytes, file_str, shim_in_scope
            )

    # Tag-driven activities & sequences
    tags = find_tags(source_text, comment_prefix="//")
    for tag in tags:
        if tag.kind == "uml-activity" and not tag.self_closed:
            act = build_activity_from_tag(tag, tree, source_bytes, file=file_str)
            if act is not None:
                project.activities.append(act)
        elif tag.kind == "uml-sequence" and not tag.self_closed:
            seq = build_sequence_from_tag(tag, tree, source_bytes, file=file_str)
            if seq is not None:
                project.sequences.append(seq)


_CLASS_LIKE_TYPES = {
    "class_declaration",
    "interface_declaration",
    "struct_declaration",
    "record_declaration",
    "record_struct_declaration",
    "enum_declaration",
}


def _visit_namespace(
    node: Node,
    parent_qn: str,
    project: Project,
    package_index: dict[str, Package],
    source: bytes,
    file_str: str,
    shim_in_scope: bool,
) -> None:
    name_node = node.child_by_field_name("name")
    name = _text(name_node, source) if name_node else "anon"
    qn = name if not parent_qn else f"{parent_qn}.{name}"
    pkg = _ensure_package(project, qn, package_index)

    body = node.child_by_field_name("body")
    if body is None:
        return
    for child in body.named_children:
        if child.type == "namespace_declaration":
            _visit_namespace(child, qn, project, package_index, source, file_str, shim_in_scope)
        elif child.type in _CLASS_LIKE_TYPES:
            _ingest_class(child, qn, project, package_index, source, file_str, shim_in_scope)


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


def _ingest_class(
    node: Node,
    package_qn: str,
    project: Project,
    package_index: dict[str, Package],
    source: bytes,
    file_str: str,
    shim_in_scope: bool,
) -> None:
    name_node = node.child_by_field_name("name")
    if name_node is None:
        return
    name = _text(name_node, source)
    qn = f"{package_qn}.{name}" if package_qn and package_qn != "__root__" else name

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
        description=_xml_doc_for(node, source),
        rules=extract_rules(node, source, shim_in_scope),
    )

    body = node.child_by_field_name("body")
    if body is not None:
        for member in body.named_children:
            _ingest_member(member, cls, source, shim_in_scope)

    cls.dependencies = _dedupe_refs(cls.dependencies, drop=cls.name)

    pkg = _ensure_package(project, package_qn, package_index)
    pkg.classes.append(cls)


def _kind_for(node: Node, source: bytes) -> ClassKind:
    if node.type == "interface_declaration":
        return "interface"
    if node.type == "struct_declaration":
        return "struct"
    if node.type in ("record_declaration", "record_struct_declaration"):
        return "record"
    if node.type == "enum_declaration":
        return "enum"
    modifiers = _modifiers(node, source)
    if "static" in modifiers:
        return "static"
    if "abstract" in modifiers:
        return "abstract"
    return "class"


def _modifiers(node: Node, source: bytes) -> list[str]:
    mods: list[str] = []
    for c in node.children:
        if c.type == "modifier":
            mods.append(_text(c, source))
    return mods


def _bases(node: Node, source: bytes) -> list[str]:
    base_list = next(
        (c for c in node.children if c.type == "base_list"), None
    )
    if base_list is None:
        return []
    bases: list[str] = []
    for child in base_list.named_children:
        bases.append(_text(child, source))
    return bases


_PASCAL_IDENT_RE = re.compile(r"^[A-Z][A-Za-z0-9_]*$")


def _body_type_refs(node: Node, source: bytes) -> list[str]:
    """Collect PascalCase identifier tokens used inside a method/ctor body.

    Heuristic (no type resolution): a PascalCase identifier in the body is a
    candidate type reference — static-call receivers (`ControlUtils.Foo()`),
    object creations (`new Foo()`), local declarations, generic args, etc.
    Downstream `resolve_association` keeps only the ones that map to a project
    class; Unity types, locals and method names simply drop out. Only the `body`
    field is walked (the block, or the arrow-expression clause for expression-
    bodied members), so `[Attribute(...)]` annotations and parameter names in
    the signature never leak in.
    """
    body = node.child_by_field_name("body")
    if body is None:
        return []
    out: list[str] = []
    seen: set[str] = set()
    stack = [body]
    while stack:
        n = stack.pop()
        stack.extend(n.children)
        if n.type == "identifier":
            txt = _text(n, source)
            if txt and txt not in seen and _PASCAL_IDENT_RE.match(txt):
                seen.add(txt)
                out.append(txt)
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


def _ingest_member(node: Node, cls: Class, source: bytes, shim_in_scope: bool) -> None:
    if node.type == "field_declaration":
        cls.attributes.extend(_attributes_from_field(node, source))
    elif node.type == "property_declaration":
        cls.attributes.append(_attribute_from_property(node, source))
    elif node.type in ("method_declaration", "constructor_declaration"):
        cls.operations.append(_operation_from_method(node, source, shim_in_scope))
        cls.dependencies.extend(_body_type_refs(node, source))
    elif node.type == "enum_member_declaration":
        name_node = node.child_by_field_name("name")
        if name_node is not None:
            cls.attributes.append(
                Attribute(
                    name=_text(name_node, source),
                    type=cls.name,
                    visibility=Visibility.PUBLIC,
                    is_static=True,
                )
            )


def _attributes_from_field(node: Node, source: bytes) -> list[Attribute]:
    # tree-sitter-c-sharp puts the type on the inner `variable_declaration`,
    # NOT on the outer `field_declaration`. Calling child_by_field_name("type")
    # on the field_declaration returns None, which silently drops the type.
    mods = _modifiers(node, source)
    vis = _visibility_from_modifiers(mods)
    is_static = "static" in mods
    is_readonly = "readonly" in mods or "const" in mods

    decl = next((c for c in node.named_children if c.type == "variable_declaration"), None)
    if decl is None:
        return []
    type_node = decl.child_by_field_name("type")
    type_text = _text(type_node, source) if type_node else ""

    out: list[Attribute] = []
    for declarator in decl.named_children:
        if declarator.type != "variable_declarator":
            continue
        name_node = declarator.child_by_field_name("name")
        if name_node is None:
            continue
        out.append(
            Attribute(
                name=_text(name_node, source),
                type=type_text,
                visibility=vis,
                is_static=is_static,
                is_readonly=is_readonly,
            )
        )
    return out


def _attribute_from_property(node: Node, source: bytes) -> Attribute:
    name_node = node.child_by_field_name("name")
    type_node = node.child_by_field_name("type")
    mods = _modifiers(node, source)
    return Attribute(
        name=_text(name_node, source) if name_node else "",
        type=_text(type_node, source) if type_node else "",
        visibility=_visibility_from_modifiers(mods),
        is_static="static" in mods,
        is_readonly="readonly" in mods,
    )


def _operation_from_method(node: Node, source: bytes, shim_in_scope: bool = False) -> Operation:
    mods = _modifiers(node, source)
    name_node = node.child_by_field_name("name")
    name = _text(name_node, source) if name_node else "<ctor>"
    return_node = node.child_by_field_name("returns") or node.child_by_field_name("type")
    return_type = _text(return_node, source) if return_node else ""

    params: list[Parameter] = []
    param_list = node.child_by_field_name("parameters")
    if param_list is not None:
        for p in param_list.named_children:
            if p.type != "parameter":
                continue
            p_name = p.child_by_field_name("name")
            p_type = p.child_by_field_name("type")
            params.append(
                Parameter(
                    name=_text(p_name, source) if p_name else "",
                    type=_text(p_type, source) if p_type else "",
                )
            )

    return Operation(
        name=name,
        parameters=params,
        return_type=return_type,
        visibility=_visibility_from_modifiers(mods),
        is_static="static" in mods,
        is_abstract="abstract" in mods,
        description=_xml_doc_for(node, source),
        rules=extract_rules(node, source, shim_in_scope),
    )


def _visibility_from_modifiers(mods: list[str]) -> Visibility:
    if "private" in mods:
        return Visibility.PRIVATE
    if "protected" in mods:
        return Visibility.PROTECTED
    if "internal" in mods and "protected" not in mods:
        return Visibility.PACKAGE
    if "public" in mods:
        return Visibility.PUBLIC
    return Visibility.PRIVATE  # C# default for class members


def _text(node: Node | None, source: bytes) -> str:
    if node is None:
        return ""
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _xml_doc_for(node: Node, source: bytes) -> str | None:
    """Collect `///` XML-doc lines immediately preceding `node`.

    Returns the text inside `<summary>` if present, otherwise the tag-stripped
    concatenation. Returns None when there's no `///` block above the node.
    """
    lines: list[str] = []
    sib = node.prev_sibling
    while sib is not None and sib.type == "comment":
        raw = _text(sib, source).strip()
        if not raw.startswith("///"):
            break
        content = raw[3:]
        if content.startswith(" "):
            content = content[1:]
        lines.insert(0, content)
        sib = sib.prev_sibling
    if not lines:
        return None
    joined = "\n".join(lines).strip()
    if not joined:
        return None
    m = re.search(r"<summary\b[^>]*>(.*?)</summary>", joined, re.DOTALL)
    if m:
        # Strip inner XML-doc tags (<see/>, <paramref/>, <c>...</c>, etc.) so
        # only the prose survives. The crefs would otherwise show up as raw
        # markup in the viewer.
        stripped = re.sub(r"<[^>]+>", "", m.group(1))
        summary = " ".join(stripped.split())
        return summary or None
    fallback = " ".join(re.sub(r"<[^>]+>", "", joined).split())
    return fallback or None
