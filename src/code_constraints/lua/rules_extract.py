"""Recognise architectural-rule annotations on Lua declarations.

Shared by the UML parser, the `cdec enforce` conformance analyzer and the
`cdec lock` fingerprinter, so "what counts as a rule" stays identical across all
three — the same contract the Python and C# extractors hold.

Lua has no decorator syntax, so tags ride in `---@cdec ...` comments directly
above the declaration. Parsing lives in `code_constraints.core.annotations`;
this module only knows where Lua puts the comments.

The one Lua-specific wrinkle: a class table is usually declared as
`local T = {}` and then given methods further down the file, so a tag written
above *any* statement that declares the table (the `local T = {}`, or a
`T.__index = T` line) attaches to the class. `rules_for_statements` folds those
sites together for the parser.
"""

from __future__ import annotations

from tree_sitter import Node

from code_constraints.core.annotations import parse_annotation, rules_before_node
from code_constraints.core.model import RuleAnnotation


def extract_rules(decl_node: Node, source: bytes) -> list[RuleAnnotation]:
    """Tags attached to a single Lua statement (`function_declaration`,
    `variable_declaration`, `assignment_statement`, …)."""
    return rules_before_node(decl_node, source)


def rules_for_statements(nodes: list[Node], source: bytes) -> list[RuleAnnotation]:
    """Union of the tags above every statement that declares one class table.

    Preserves source order and drops exact duplicates, so tagging both the
    `local T = {}` and the `T.__index = T` line doesn't double up.
    """
    out: list[RuleAnnotation] = []
    for node in nodes:
        for rule in rules_before_node(node, source):
            if rule not in out:
                out.append(rule)
    return out


def comment_is_rule_tag(node: Node, source: bytes) -> bool:
    """True when `node` is a comment carrying a `@cdec` tag.

    The fingerprinter drops these from the digest so applying or removing a lock
    never changes the hash of the body it guards.
    """
    if node.type != "comment":
        return False
    text = source[node.start_byte : node.end_byte].decode("utf-8", "replace")
    return parse_annotation(text) is not None
