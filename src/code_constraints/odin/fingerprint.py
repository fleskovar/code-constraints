"""AST fingerprinting for Odin (`cdec lock`, Engine C).

Digests come from the tree-sitter tree via `core.ts_fingerprint`, so a locked
element survives reformatting and relocation within its file.

Odin-specific concerns:

* **Tags are comments**, so the `//@cdec locked` line is dropped from the digest
  explicitly rather than incidentally — otherwise `include_docstrings` would let
  applying a lock change the very digest it records.
* **Target names must match the UML model**, because a target an agent reads
  from `cdec lock list` has to be the target `cdec lock set` accepts. Procedures
  are therefore resolved to their receiver struct exactly as the parser does,
  which needs the same two-phase walk (structs first, then procedures) and the
  same helpers — imported from `odin.parser` rather than re-derived, so the two
  can't drift apart.
"""

from __future__ import annotations

from pathlib import Path

import tree_sitter_odin
from tree_sitter import Language, Node, Parser

from code_constraints.core.ts_fingerprint import digest_members
from code_constraints.lock.model import LOCK_RULE, LockTarget
from code_constraints.odin.parser import (
    _TYPE_DECL_TYPES,
    _package_name,
    _parameters,
    _receiver_name,
    _should_skip,
    _text,
)
from code_constraints.odin.rules_extract import comment_is_rule_tag, extract_rules

DIGEST_ALGO = "odin-ts/1"

_LANG = Language(tree_sitter_odin.language())
_PARSER = Parser(_LANG)


def collect_lockables(
    root: str | Path, *, include_docstrings: bool = False
) -> list[LockTarget]:
    root_path = Path(root).resolve()
    files: list[tuple[Path, bytes, Node, str]] = []
    # (package_qn, struct name) -> qualified name, for receiver resolution.
    struct_index: dict[tuple[str, str], str] = {}
    out: list[LockTarget] = []

    # Phase 1: every type declaration, indexed for phase 2.
    for odin_file in sorted(root_path.rglob("*.odin")):
        if _should_skip(odin_file):
            continue
        try:
            source = odin_file.read_bytes()
        except OSError:
            continue
        tree = _PARSER.parse(source)
        rel = odin_file.relative_to(root_path)
        package_qn = _package_name(tree.root_node, source, rel)
        files.append((rel, source, tree.root_node, package_qn))

        for child in tree.root_node.named_children:
            if child.type not in _TYPE_DECL_TYPES:
                continue
            name_node = next((c for c in child.children if c.type == "identifier"), None)
            if name_node is None:
                continue
            name = _text(name_node, source)
            qn = f"{package_qn}.{name}" if package_qn != "__root__" else name
            struct_index[(package_qn, name)] = qn
            out.append(
                _target(
                    [(child, source)], qn, "class", rel.as_posix(), include_docstrings
                )
            )

    # Phase 2: procedures, grouped by owner so same-named siblings share a target.
    groups: dict[str, list[tuple[Node, bytes]]] = {}
    locations: dict[str, str] = {}
    for rel, source, root_node, package_qn in files:
        for child in root_node.named_children:
            if child.type != "procedure_declaration":
                continue
            name_node = next((c for c in child.children if c.type == "identifier"), None)
            proc_node = next((c for c in child.children if c.type == "procedure"), None)
            if name_node is None or proc_node is None:
                continue
            owner = _owner_qn(proc_node, source, package_qn, struct_index, rel)
            target = f"{owner}.{_text(name_node, source)}"
            groups.setdefault(target, []).append((child, source))
            locations.setdefault(target, rel.as_posix())

    for target, members in groups.items():
        out.append(
            _target(members, target, "method", locations[target], include_docstrings)
        )

    return out


def _owner_qn(
    proc_node: Node,
    source: bytes,
    package_qn: str,
    struct_index: dict[tuple[str, str], str],
    rel: Path,
) -> str:
    """The receiver struct's qualified name, or the file's synthetic module class."""
    params = _parameters(proc_node, source)
    name = _receiver_name(params)
    if name:
        same_package = struct_index.get((package_qn, name))
        if same_package is not None:
            return same_package
        matches = [qn for (_pkg, n), qn in struct_index.items() if n == name]
        if len(matches) == 1:
            return matches[0]
    return f"{package_qn}.{rel.stem}" if package_qn != "__root__" else rel.stem


def _target(
    members: list[tuple[Node, bytes]],
    target: str,
    kind: str,
    file: str,
    include_docstrings: bool,
) -> LockTarget:
    def drop(node: Node, source: bytes) -> bool:
        if node.type != "comment":
            return False
        # A rule tag is never part of the implementation, whatever the
        # docstring setting: applying or removing `//@cdec locked` must leave
        # the digest of the body it guards untouched.
        if comment_is_rule_tag(node, source):
            return True
        return not include_docstrings

    declared = False
    params: dict[str, str] = {}
    for node, source in members:
        for rule in extract_rules(node, source):
            if rule.name == LOCK_RULE:
                declared = True
                params = {**rule.kwargs, **params} if params else dict(rule.kwargs)

    return LockTarget(
        target=target,
        kind=kind,  # type: ignore[arg-type]
        digest=digest_members(members, drop),
        algo=DIGEST_ALGO,
        file=file,
        line=members[0][0].start_point[0] + 1,
        declared=declared,
        params=params,
    )
