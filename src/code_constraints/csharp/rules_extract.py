"""Recognise architectural-rule attributes on C# declarations.

Shared by the UML parser and the `cdec enforce` conformance analyzer. An
attribute counts as a rule only when the file has `using CodeConstraints.Rules;`
(or the attribute is written fully qualified) — so a same-named user attribute
is never misread as a rule.
"""

from __future__ import annotations

from tree_sitter import Node

from code_constraints.core.model import RuleAnnotation
from code_constraints.core.rules import CSHARP_SHIM_NAMESPACE, by_csharp_name


def using_has_shim(root: Node, source: bytes) -> bool:
    """True when the compilation unit imports the shim namespace."""
    stack = [root]
    while stack:
        node = stack.pop()
        if node.type == "using_directive" and CSHARP_SHIM_NAMESPACE in _text(node, source):
            return True
        stack.extend(node.children)
    return False


def extract_rules(decl_node: Node, source: bytes, shim_in_scope: bool) -> list[RuleAnnotation]:
    rules: list[RuleAnnotation] = []
    for child in decl_node.children:
        if child.type != "attribute_list":
            continue
        for attr in child.named_children:
            if attr.type != "attribute":
                continue
            name_node = attr.child_by_field_name("name")
            raw_name = _text(name_node, source) if name_node else ""
            if not raw_name:
                continue
            qualified_shim = raw_name.startswith(CSHARP_SHIM_NAMESPACE + ".")
            if not (shim_in_scope or qualified_shim):
                continue
            spec = by_csharp_name(raw_name.rsplit(".", 1)[-1])
            if spec is None:
                continue
            args, kwargs = _attr_args(attr, source)
            rules.append(RuleAnnotation(name=spec.id, args=args, kwargs=kwargs))
    return rules


def _attr_args(attr: Node, source: bytes) -> tuple[list[str], dict[str, str]]:
    args: list[str] = []
    kwargs: dict[str, str] = {}
    arglist = next(
        (c for c in attr.children if c.type == "attribute_argument_list"), None
    )
    if arglist is None:
        return args, kwargs
    for a in arglist.children:
        if a.type != "attribute_argument":
            continue
        kids = a.children
        # Named arg: `identifier = value` (or `identifier : value`).
        sep = next((i for i, c in enumerate(kids) if c.type in ("=", ":")), None)
        if sep is not None and sep >= 1 and kids[sep - 1].type == "identifier":
            name = _text(kids[sep - 1], source)
            value = next((c for c in kids[sep + 1 :] if c.is_named), None)
            kwargs[name] = _text(value, source) if value else ""
        else:
            value = next((c for c in kids if c.is_named), None)
            args.append(_text(value, source) if value else "")
    return args, kwargs


def _text(node: Node | None, source: bytes) -> str:
    if node is None:
        return ""
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")
