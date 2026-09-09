"""AST fingerprinting for C# (`cdec lock`, Engine C).

The C# twin of `code_constraints.python.fingerprint`. Digests come from the tree-sitter
concrete syntax tree, which is already whitespace-insensitive (indentation and
newlines produce no nodes), so a locked member survives reformatting and
relocation within its file. Comments *are* nodes here, so they're dropped
explicitly, as is the `[Locked]` attribute itself.

Unlike the Python side we walk anonymous children too: operators and
punctuation (`+` vs `-`, `==` vs `!=`) are anonymous tokens, and skipping them
would make `a + b` and `a - b` hash identically.
"""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import tree_sitter_c_sharp
from tree_sitter import Language, Node, Parser

from code_constraints.core.rules import CSHARP_SHIM_NAMESPACE, by_csharp_name
from code_constraints.csharp.rules_extract import extract_rules, using_has_shim
from code_constraints.lock.model import LOCK_RULE, LockTarget

DIGEST_ALGO = "cs-ts/1"

_LANG = Language(tree_sitter_c_sharp.language())
_PARSER = Parser(_LANG)

_SKIP_DIR_NAMES = {"bin", "obj", ".git", "packages", "TestResults"}

_CLASS_LIKE = {
    "class_declaration",
    "interface_declaration",
    "struct_declaration",
    "record_declaration",
    "record_struct_declaration",
    "enum_declaration",
}
_MEMBER_LIKE = {
    "method_declaration",
    "constructor_declaration",
    "destructor_declaration",
    "property_declaration",
    "operator_declaration",
    "indexer_declaration",
}
_COMMENT_TYPES = {"comment"}


def collect_lockables(
    root: str | Path, *, include_docstrings: bool = False
) -> list[LockTarget]:
    """Walk `root` and return every lockable declaration with its digest.

    `include_docstrings` controls whether `///` XML-doc comments count: they are
    `comment` nodes, so the default (False) drops them along with every other
    comment, and True keeps documentation comments in the digest.
    """
    root_path = Path(root).resolve()
    out: list[LockTarget] = []
    for cs_file in sorted(root_path.rglob("*.cs")):
        if any(part in _SKIP_DIR_NAMES for part in cs_file.parts):
            continue
        try:
            source = cs_file.read_bytes()
        except OSError:
            continue
        tree = _PARSER.parse(source)
        rel = cs_file.relative_to(root_path).as_posix()
        shim = using_has_shim(tree.root_node, source)
        _collect_unit(tree.root_node, source, rel, shim, include_docstrings, out)
    return out


def _collect_unit(
    root: Node,
    source: bytes,
    file: str,
    shim: bool,
    include_docstrings: bool,
    out: list[LockTarget],
) -> None:
    file_scoped = ""
    for child in root.named_children:
        if child.type == "namespace_declaration":
            _collect_namespace(child, "", source, file, shim, include_docstrings, out)
        elif child.type == "file_scoped_namespace_declaration":
            name_node = child.child_by_field_name("name")
            file_scoped = _text(name_node, source) if name_node else "anon"
        elif child.type in _CLASS_LIKE:
            _collect_class(
                child, file_scoped, source, file, shim, include_docstrings, out
            )


def _collect_namespace(
    node: Node,
    parent_qn: str,
    source: bytes,
    file: str,
    shim: bool,
    include_docstrings: bool,
    out: list[LockTarget],
) -> None:
    name_node = node.child_by_field_name("name")
    name = _text(name_node, source) if name_node else "anon"
    qn = f"{parent_qn}.{name}" if parent_qn else name
    body = node.child_by_field_name("body")
    if body is None:
        return
    for child in body.named_children:
        if child.type == "namespace_declaration":
            _collect_namespace(child, qn, source, file, shim, include_docstrings, out)
        elif child.type in _CLASS_LIKE:
            _collect_class(child, qn, source, file, shim, include_docstrings, out)


def _collect_class(
    node: Node,
    package_qn: str,
    source: bytes,
    file: str,
    shim: bool,
    include_docstrings: bool,
    out: list[LockTarget],
) -> None:
    name_node = node.child_by_field_name("name")
    if name_node is None:
        return
    name = _text(name_node, source)
    target = f"{package_qn}.{name}" if package_qn else name

    _emit(node, target, "class", source, file, shim, include_docstrings, out)

    body = node.child_by_field_name("body")
    if body is None:
        return

    # Group same-named members so overloads collapse into one target.
    groups: dict[str, list[Node]] = {}
    for member in body.named_children:
        if member.type in _CLASS_LIKE:
            _collect_class(member, target, source, file, shim, include_docstrings, out)
        elif member.type in _MEMBER_LIKE:
            member_name = _member_name(member, source)
            if member_name:
                groups.setdefault(member_name, []).append(member)

    for member_name, nodes in groups.items():
        _emit(
            nodes,
            f"{target}.{member_name}",
            "method",
            source,
            file,
            shim,
            include_docstrings,
            out,
        )


def _emit(
    nodes: Node | list[Node],
    target: str,
    kind: str,
    source: bytes,
    file: str,
    shim: bool,
    include_docstrings: bool,
    out: list[LockTarget],
) -> None:
    group = nodes if isinstance(nodes, list) else [nodes]
    digests = sorted(
        sha256(_canonical(n, source, shim, include_docstrings).encode("utf-8")).hexdigest()
        for n in group
    )
    digest = (
        digests[0]
        if len(digests) == 1
        else sha256(("group:" + "|".join(digests)).encode("utf-8")).hexdigest()
    )

    declared = False
    params: dict[str, str] = {}
    for n in group:
        for rule in extract_rules(n, source, shim):
            if rule.name == LOCK_RULE:
                declared = True
                params = {**rule.kwargs, **params} if params else dict(rule.kwargs)

    out.append(
        LockTarget(
            target=target,
            kind=kind,  # type: ignore[arg-type]
            digest=digest,
            algo=DIGEST_ALGO,
            file=file,
            line=group[0].start_point[0] + 1,
            declared=declared,
            params=params,
        )
    )


# ---------- digest ----------

def _canonical(node: Node, source: bytes, shim: bool, include_docstrings: bool) -> str:
    if node.type in _COMMENT_TYPES and not include_docstrings:
        return ""
    if node.type == "attribute" and _is_lock_attribute(node, source, shim):
        return ""
    if node.type == "attribute_list" and not _has_kept_attribute(node, source, shim):
        # Dropping `[Locked]` must not leave an empty `[]` in the digest, or
        # adding/removing a lock would change the enclosing member's hash.
        return ""
    if node.child_count == 0:
        text = _text(node, source).strip()
        return f"({node.type} {text!r})" if node.is_named else f"({text!r})"
    parts = [
        p
        for p in (
            _canonical(c, source, shim, include_docstrings) for c in node.children
        )
        if p
    ]
    return f"({node.type} {' '.join(parts)})"


def _is_lock_attribute(attr: Node, source: bytes, shim: bool) -> bool:
    """True when this single `attribute` node is the lock tag.

    `extract_rules` works per *declaration* and returns catalog ids, which loses
    the node-to-tag mapping we need here, so this mirrors its gating: an
    attribute counts only when the shim namespace is imported or the attribute
    is written fully qualified.
    """
    name_node = attr.child_by_field_name("name")
    raw = _text(name_node, source) if name_node else ""
    if not raw:
        return False
    if not (shim or raw.startswith(CSHARP_SHIM_NAMESPACE + ".")):
        return False
    spec = by_csharp_name(raw.rsplit(".", 1)[-1])
    return spec is not None and spec.id == LOCK_RULE


def _has_kept_attribute(attr_list: Node, source: bytes, shim: bool) -> bool:
    for child in attr_list.named_children:
        if child.type != "attribute":
            continue
        if not _is_lock_attribute(child, source, shim):
            return True
    return False


def _member_name(node: Node, source: bytes) -> str:
    name_node = node.child_by_field_name("name")
    if name_node is not None:
        return _text(name_node, source)
    if node.type == "constructor_declaration":
        return ".ctor"
    if node.type == "destructor_declaration":
        return ".dtor"
    if node.type == "indexer_declaration":
        return "this[]"
    return ""


def _text(node: Node | None, source: bytes) -> str:
    if node is None:
        return ""
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")
