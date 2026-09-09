"""Recognise architectural-rule macros on Julia declarations.

Shared by the UML parser, the `cdec enforce` conformance analyzer and the
`cdec lock` fingerprinter, so "what counts as a rule" stays identical across all
three — the same contract the Python and C# extractors hold. A macro counts as a
rule only when the file brings the shim module into scope (`using CdecRules` /
`import CdecRules`), so a user's own `@sealed` is never misread.

Two shapes worth knowing, both of which this module folds into one
`(rules, definition)` pair via `unwrap_macros`:

1. **Stacked tags nest.** Real Julia parses `@sealed @layer "domain" struct X end`
   as `@sealed(@layer("domain", struct X end))` — one argument, itself a
   macrocall. tree-sitter instead emits the inner macrocall and the struct as
   *siblings* inside the outer `macro_argument_list`. `unwrap_macros` handles
   both by scanning the argument list for nested macrocalls and for the
   definition, then recursing.

2. **Arguments are space-separated, not parenthesised.** `@locked reason="why"
   function f() end` puts each keyword in its own `assignment` node alongside the
   definition. That collides with Julia's short-form function syntax, which is
   *also* an `assignment` (`f(x::T) = x`); the two are told apart by their
   left-hand side (`identifier` for a keyword, `call_expression` for a
   definition). `@layer("domain")` — the parenthesised form — is a syntax error
   in Julia, but the grammar accepts it, so `_macro_args` reads an
   `argument_list` too rather than silently dropping the tag.
"""

from __future__ import annotations

from tree_sitter import Node

from code_constraints.core.model import RuleAnnotation
from code_constraints.core.rules import JULIA_SHIM_MODULES, by_julia_name

# Node types that can be the definition a tag decorates.
DEFINITION_TYPES = frozenset(
    {
        "struct_definition",
        "abstract_definition",
        "primitive_definition",
        "function_definition",
        "assignment",  # short-form function definition: `f(x::T) = ...`
        "const_statement",
        "macro_definition",
    }
)


def using_has_shim(root: Node, source: bytes) -> bool:
    """True when the file brings the shim module into scope."""
    stack = [root]
    while stack:
        node = stack.pop()
        if node.type in ("using_statement", "import_statement"):
            text = _text(node, source)
            if any(mod in text for mod in JULIA_SHIM_MODULES):
                return True
        stack.extend(node.children)
    return False


def unwrap_macros(node: Node, source: bytes, shim_in_scope: bool) -> tuple[
    list[RuleAnnotation], Node | None
]:
    """Peel every macro wrapping `node` and return its rules + the definition.

    For a node that isn't a macrocall this is `([], node)`. Macros that aren't in
    the rule catalog are peeled too — their arguments still contain the
    definition, so an unrelated `@inline`/`Base.@kwdef` wrapper doesn't hide the
    struct from the parser — but they contribute no `RuleAnnotation`.
    """
    if node.type != "macrocall_expression":
        return [], node

    rules: list[RuleAnnotation] = []
    definition: Node | None = None
    pending: list[Node] = [node]

    while pending:
        current = pending.pop(0)
        if current.type != "macrocall_expression":
            continue
        spec_id = _macro_rule_id(current, source, shim_in_scope)
        args, kwargs, nested, found = _macro_args(current, source)
        if spec_id is not None:
            rules.append(RuleAnnotation(name=spec_id, args=args, kwargs=kwargs))
        if found is not None and definition is None:
            definition = found
        pending.extend(nested)

    if definition is not None and definition.type == "macrocall_expression":
        inner_rules, inner_def = unwrap_macros(definition, source, shim_in_scope)
        rules.extend(inner_rules)
        definition = inner_def

    return rules, definition


def extract_rules(node: Node, source: bytes, shim_in_scope: bool) -> list[RuleAnnotation]:
    """Just the rules from the macros wrapping `node`."""
    rules, _ = unwrap_macros(node, source, shim_in_scope)
    return rules


def foreign_macros(node: Node, source: bytes, shim_in_scope: bool) -> list[str]:
    """Text of every non-catalog macro applied to `node`, sorted.

    The fingerprinter digests the *unwrapped* definition, because the grammar
    flattens stacked macros into siblings and there is no way to peel one tag
    while re-serialising the rest of the chain around it. Folding this list into
    the digest restores what unwrapping would otherwise lose: adding or removing
    an `@inline` is a real change, while adding or removing `@locked` is not.
    """
    out: list[str] = []
    pending = [node]
    while pending:
        current = pending.pop(0)
        if current.type != "macrocall_expression":
            continue
        ident = next((c for c in current.children if c.type == "macro_identifier"), None)
        if ident is not None and _macro_rule_id(current, source, shim_in_scope) is None:
            prefix = (
                _text(current.children[0], source) + "."
                if current.children and current.children[0].type == "identifier"
                else ""
            )
            out.append(prefix + _text(ident, source))
        _args, _kwargs, nested, found = _macro_args(current, source)
        pending.extend(nested)
        if found is not None and found.type == "macrocall_expression":
            pending.append(found)
    return sorted(out)


def macro_is_rule(node: Node, source: bytes, shim_in_scope: bool, rule_id: str) -> bool:
    """True when `node` is a `macrocall_expression` for the given catalog rule.

    The fingerprinter needs the node-to-tag mapping that `extract_rules` loses,
    to drop the lock tag from a digest without dropping the definition it wraps.
    """
    if node.type != "macrocall_expression":
        return False
    return _macro_rule_id(node, source, shim_in_scope) == rule_id


def _macro_rule_id(node: Node, source: bytes, shim_in_scope: bool) -> str | None:
    if not shim_in_scope:
        return None
    ident = next((c for c in node.children if c.type == "macro_identifier"), None)
    if ident is None:
        return None
    # A qualified call (`Base.@kwdef`) puts an identifier + `.` before the macro
    # identifier; those are never our tags.
    if node.children and node.children[0].type == "identifier":
        return None
    spec = by_julia_name(_text(ident, source))
    return spec.id if spec else None


def _macro_args(
    node: Node, source: bytes
) -> tuple[list[str], dict[str, str], list[Node], Node | None]:
    """Split a macrocall's arguments into positional / keyword / nested macros /
    the decorated definition."""
    args: list[str] = []
    kwargs: dict[str, str] = {}
    nested: list[Node] = []
    definition: Node | None = None

    arglist = next(
        (
            c
            for c in node.children
            if c.type in ("macro_argument_list", "argument_list")
        ),
        None,
    )
    if arglist is None:
        return args, kwargs, nested, definition

    for child in arglist.named_children:
        if child.type == "macrocall_expression":
            nested.append(child)
        elif child.type in ("assignment", "named_argument") and _is_keyword(child):
            name, value = _keyword_parts(child, source)
            if name:
                kwargs[name] = value
        elif child.type in DEFINITION_TYPES:
            if definition is None:
                definition = child
        else:
            args.append(_text(child, source))

    return args, kwargs, nested, definition


def _is_keyword(node: Node) -> bool:
    """`reason="why"` is a keyword argument; `f(x::T) = x` is a definition."""
    if node.type == "named_argument":
        return True
    first = node.named_children[0] if node.named_children else None
    return first is not None and first.type == "identifier"


def _keyword_parts(node: Node, source: bytes) -> tuple[str, str]:
    named = node.named_children
    if len(named) < 2:
        return "", ""
    return _text(named[0], source), _text(named[-1], source)


def _text(node: Node | None, source: bytes) -> str:
    if node is None:
        return ""
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")
