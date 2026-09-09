"""Canonical AST serialisation for tree-sitter-backed lock fingerprints.

The shared half of Engine C (`cdec lock`) for every tree-sitter language. It
answers only "what string represents this subtree"; each language's
`fingerprint.py` owns discovery, target naming, and which nodes to drop.

The invariants a fingerprinter must preserve — the same ones documented on
`code_constraints.csharp.fingerprint`, which predates this module and keeps its
own copy:

* **Anonymous children are walked.** Operators and punctuation are anonymous
  tokens, so skipping them would hash `a + b` and `a - b` identically.
* **Whitespace never appears.** tree-sitter emits no nodes for indentation or
  newlines, so a locked body survives reformatting and relocation for free.
* **Comments are dropped** unless the caller keeps them, and the rule *tag*
  itself is always dropped — applying or removing a lock must not change the
  digest of the body it guards.
* **Changing this serialiser must bump the caller's algo id.** A mismatch then
  surfaces as an `algo-mismatch` violation ("re-baseline") rather than as a
  false "implementation changed".
"""

from __future__ import annotations

from hashlib import sha256
from typing import Callable, Sequence

from tree_sitter import Node

# Returns True for a node that must not contribute to the digest. Takes the
# source alongside the node because a group's members can come from different
# files (Odin and Julia declare a type's operations at package scope, so two
# same-named members need not share a file).
DropFn = Callable[[Node, bytes], bool]

# Extra text folded into a member's digest beyond its serialised subtree. Lets a
# language account for something outside the node it digests — Julia uses it to
# keep non-rule macro wrappers significant while digesting the unwrapped
# definition. Return "" to add nothing.
ExtraFn = Callable[[Node, bytes], str]


def canonical(node: Node, source: bytes, drop: DropFn) -> str:
    """Serialise `node` to a canonical, position-independent string."""
    if drop(node, source):
        return ""
    if node.child_count == 0:
        text = _text(node, source).strip()
        return f"({node.type} {text!r})" if node.is_named else f"({text!r})"
    parts = [p for p in (canonical(c, source, drop) for c in node.children) if p]
    if not parts:
        # Every child was dropped; keep the node's own identity so an emptied
        # wrapper still differs from the wrapper being absent.
        return f"({node.type})"
    return f"({node.type} {' '.join(parts)})"


def digest_members(
    members: Sequence[tuple[Node, bytes]], drop: DropFn, extra: ExtraFn | None = None
) -> str:
    """Digest a group of same-named members as one target.

    Overloads, `@property`/setter pairs, and multiple-dispatch methods collapse
    into a single digest over their sorted member digests, so adding an overload
    to a locked name is a violation in its own right and no ordinal
    disambiguator is needed. Sorting also makes the digest independent of the
    order the files happened to be walked in.
    """
    digests = sorted(
        sha256(
            (canonical(node, source, drop) + _suffix(extra, node, source)).encode("utf-8")
        ).hexdigest()
        for node, source in members
    )
    if len(digests) == 1:
        return digests[0]
    return sha256(("group:" + "|".join(digests)).encode("utf-8")).hexdigest()


def _suffix(extra: ExtraFn | None, node: Node, source: bytes) -> str:
    if extra is None:
        return ""
    text = extra(node, source)
    return f"|extra:{text}" if text else ""


def _text(node: Node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")
