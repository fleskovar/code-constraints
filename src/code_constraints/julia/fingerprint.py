"""AST fingerprinting for Julia (`cdec lock`, Engine C).

Digests come from the tree-sitter tree via `core.ts_fingerprint`, so a locked
element survives reformatting and relocation within its file.

Julia-specific concerns:

* **Tags wrap the definition.** `@locked function f(...) end` is a macrocall with
  the function inside it, not a comment above it, so the digest is taken with an
  `unwrap` that peels *rule* macros only. A non-rule macro (`@inline`,
  `Base.@kwdef`) stays in the digest, so adding or removing one is a real
  change, while applying or removing `@locked` is not.
* **Multiple dispatch means one name, many methods.** Every method of
  `settle(::Invoice, …)` groups into the single target `Billing.Invoice.settle`,
  so adding a new dispatch to a locked name is itself a lock violation. Those
  methods can live in different files, which is why the group carries its own
  source per member.
* **Target names must match the UML model**, so receivers resolve exactly as the
  parser resolves them — using helpers imported from `julia.parser` rather than
  re-derived, so the two can't drift apart.
"""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import tree_sitter_julia
from tree_sitter import Language, Node, Parser

from code_constraints.core.model import Parameter
from code_constraints.core.ts_fingerprint import digest_members
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
from code_constraints.julia.rules_extract import (
    foreign_macros,
    unwrap_macros,
    using_has_shim,
)
from code_constraints.lock.model import LOCK_RULE, LockTarget

DIGEST_ALGO = "jl-ts/1"

_COMMENT_TYPES = frozenset({"line_comment", "block_comment"})

_LANG = Language(tree_sitter_julia.language())
_PARSER = Parser(_LANG)


def collect_lockables(
    root: str | Path, *, include_docstrings: bool = False
) -> list[LockTarget]:
    root_path = Path(root).resolve()
    out: list[LockTarget] = []
    # (package_qn, struct name) -> qualified name.
    struct_index: dict[tuple[str, str], str] = {}
    # Structs and functions found per file, kept for the second phase.
    functions: list[tuple[Node, bytes, str, str, bool]] = []
    struct_nodes: list[tuple[Node, bytes, str, str, bool]] = []

    for jl_file in sorted(root_path.rglob("*.jl")):
        if _should_skip(jl_file):
            continue
        try:
            source = jl_file.read_bytes()
        except OSError:
            continue
        tree = _PARSER.parse(source)
        rel = jl_file.relative_to(root_path)
        shim = using_has_shim(tree.root_node, source)
        _scan(
            tree.root_node,
            source,
            _qualified_package_name(rel),
            rel.stem,
            rel.as_posix(),
            shim,
            struct_index,
            struct_nodes,
            functions,
        )

    for node, source, qn, file, shim in struct_nodes:
        out.append(_target([(node, source)], qn, "class", file, shim, include_docstrings))

    groups: dict[str, list[tuple[Node, bytes]]] = {}
    meta: dict[str, tuple[str, bool]] = {}
    for node, source, package_qn, file, shim in functions:
        rules, definition = unwrap_macros(node, source, shim)
        if definition is None:
            continue
        operation = _operation(definition, rules, source)
        if operation is None:
            continue
        owner = _owner_qn(operation.parameters, package_qn, struct_index, file)
        target = f"{owner}.{operation.name}"
        groups.setdefault(target, []).append((node, source))
        meta.setdefault(target, (file, shim))

    for target, members in groups.items():
        file, shim = meta[target]
        out.append(_target(members, target, "method", file, shim, include_docstrings))

    return out


def _scan(
    parent: Node,
    source: bytes,
    package_qn: str,
    stem: str,
    file: str,
    shim: bool,
    struct_index: dict[tuple[str, str], str],
    struct_nodes: list[tuple[Node, bytes, str, str, bool]],
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
            _scan(
                node, source, nested, stem, file, shim,
                struct_index, struct_nodes, functions,
            )
        elif node.type in _TYPE_DEFINITION_TYPES:
            head = next((c for c in node.children if c.type == "type_head"), None)
            if head is None:
                continue
            name, _bases = _type_head_parts(head, source)
            if not name:
                continue
            qn = f"{package_qn}.{name}" if package_qn != "__root__" else name
            struct_index[(package_qn, name)] = qn
            # `child`, not `node`: the tag wrapper is part of the declaration and
            # the unwrap callback peels it during digesting.
            struct_nodes.append((child, source, qn, file, shim))
        elif node.type == "function_definition" or _is_short_function(node):
            functions.append((child, source, package_qn, file, shim))


def _owner_qn(
    params: list[Parameter],
    package_qn: str,
    struct_index: dict[tuple[str, str], str],
    file: str,
) -> str:
    if params and params[0].type:
        name = _base_name(params[0].type)
        same_package = struct_index.get((package_qn, name))
        if same_package is not None:
            return same_package
        matches = [qn for (_pkg, n), qn in struct_index.items() if n == name]
        if len(matches) == 1:
            return matches[0]
    stem = Path(file).stem
    return f"{package_qn}.{stem}" if package_qn != "__root__" else stem


def _target(
    members: list[tuple[Node, bytes]],
    target: str,
    kind: str,
    file: str,
    shim: bool,
    include_docstrings: bool,
) -> LockTarget:
    def drop(node: Node, _source: bytes) -> bool:
        # tree-sitter-julia splits comments into `line_comment` / `block_comment`
        # — there is no `comment` node type, unlike every other grammar here. A
        # Julia docstring is a `string_literal` preceding the definition, not a
        # comment, so it is left alone: it belongs to the definition's structure.
        return node.type in _COMMENT_TYPES and not include_docstrings

    declared = False
    params: dict[str, str] = {}
    # Digest the definition each tag wraps, never the macrocall: that is what
    # makes applying or removing `@locked` leave the digest untouched.
    definitions: list[tuple[Node, bytes]] = []
    for node, source in members:
        rules, definition = unwrap_macros(node, source, shim)
        definitions.append((definition if definition is not None else node, source))
        for rule in rules:
            if rule.name == LOCK_RULE:
                declared = True
                params = {**rule.kwargs, **params} if params else dict(rule.kwargs)

    # Foreign macros are read from the *original* members (which still carry the
    # wrappers) and folded in beside the unwrapped digest.
    macro_texts = sorted(
        text
        for node, source in members
        for text in [",".join(foreign_macros(node, source, shim))]
        if text
    )
    digest_base = digest_members(definitions, drop)
    digest = (
        digest_base
        if not macro_texts
        else sha256(
            (digest_base + "|macros:" + "|".join(macro_texts)).encode("utf-8")
        ).hexdigest()
    )

    return LockTarget(
        target=target,
        kind=kind,  # type: ignore[arg-type]
        digest=digest,
        algo=DIGEST_ALGO,
        file=file,
        line=members[0][0].start_point[0] + 1,
        declared=declared,
        params=params,
    )
