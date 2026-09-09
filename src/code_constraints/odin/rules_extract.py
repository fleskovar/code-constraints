"""Recognise architectural-rule annotations on Odin declarations.

Shared by the UML parser, the `cdec enforce` conformance analyzer and the
`cdec lock` fingerprinter, so "what counts as a rule" stays identical across all
three — the same contract the Python and C# extractors hold.

Odin's `@(...)` attributes are a closed set the compiler validates, so tags ride
in `//@cdec ...` comments directly above the declaration instead. Parsing lives
in `code_constraints.core.annotations`; this module only knows where Odin puts
the comments.
"""

from __future__ import annotations

from tree_sitter import Node

from code_constraints.core.annotations import rules_before_node
from code_constraints.core.model import RuleAnnotation


def extract_rules(decl_node: Node, source: bytes) -> list[RuleAnnotation]:
    """Tags attached to an Odin declaration (`struct_declaration`,
    `procedure_declaration`, …)."""
    return rules_before_node(decl_node, source)


def comment_is_rule_tag(node: Node, source: bytes) -> bool:
    """True when `node` is a comment carrying a `@cdec` tag.

    The fingerprinter drops these from the digest so applying or removing a lock
    never changes the hash of the body it guards.
    """
    if node.type != "comment":
        return False
    from code_constraints.core.annotations import parse_annotation

    text = source[node.start_byte : node.end_byte].decode("utf-8", "replace")
    return parse_annotation(text) is not None
