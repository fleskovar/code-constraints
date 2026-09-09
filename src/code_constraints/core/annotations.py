"""Parse `@cdec` annotation comments into `RuleAnnotation`s.

The tag carrier for languages with no user-extensible decorator or attribute
syntax — currently Lua and Odin (see the `ANNOTATION_MARKER` note in
`code_constraints.core.rules` for why neither can use a no-op shim declaration).
A tag is a namespaced comment sitting directly above the declaration:

    ---@cdec sealed                              (Lua)
    ---@cdec locked(reason = "agreed", owner = "ann")
    //@cdec layer("domain")                      (Odin)
    //@cdec no_instantiation(allow = ["Builder"])

Shared by `code_constraints.{lua,odin}.rules_extract` so "what counts as a rule"
stays identical across the two, exactly as `rules_extract` is shared between each
language's UML parser and its enforce/lock analyzers.

Like `core.tags`, the parser is deliberately forgiving: an unparseable annotation
is skipped rather than raising, so a typo never fails a whole parse.
"""

from __future__ import annotations

import ast
import re
from typing import TYPE_CHECKING

from code_constraints.core.model import RuleAnnotation
from code_constraints.core.rules import ANNOTATION_MARKER, by_annotation_name

if TYPE_CHECKING:
    from tree_sitter import Node

# `@cdec <name>` optionally followed by an argument list. Leading comment
# punctuation (`--`, `//`, `-`, whitespace) is skipped by searching for the
# marker rather than anchoring at the line start.
_ANNOTATION_RE = re.compile(
    re.escape(ANNOTATION_MARKER) + r"\s+([A-Za-z_][A-Za-z0-9_]*)\s*(\(.*)?$",
    re.DOTALL,
)


def parse_annotation(text: str) -> RuleAnnotation | None:
    """Parse one comment's text into a `RuleAnnotation`, or None if it isn't a
    recognised `@cdec` tag."""
    idx = text.find(ANNOTATION_MARKER)
    if idx < 0:
        return None
    match = _ANNOTATION_RE.search(text, idx)
    if match is None:
        return None
    spec = by_annotation_name(match.group(1))
    if spec is None:
        return None
    args, kwargs = _parse_args(match.group(2) or "")
    return RuleAnnotation(name=spec.id, args=args, kwargs=kwargs)


def rules_from_comments(texts: list[str]) -> list[RuleAnnotation]:
    """Parse a run of comment texts (outermost first) into rule annotations,
    skipping every line that isn't a `@cdec` tag."""
    out: list[RuleAnnotation] = []
    for text in texts:
        rule = parse_annotation(text)
        if rule is not None:
            out.append(rule)
    return out


def literal_set(source_text: str) -> set[str]:
    """Parse a rule argument holding a list of names into a set of strings.

    Handles every shape the languages here produce for `allow=` / `creates=`,
    because each is also a Python literal: `["Money"]` (Odin, Julia, C#),
    `{"Money"}` (Lua table), `['Money']` (Python). Tolerant by design — an
    unparseable value yields an empty set rather than failing the run, matching
    `python.conformance._str_list`.
    """
    if not source_text:
        return set()
    try:
        value = ast.literal_eval(source_text.strip())
    except (ValueError, SyntaxError):
        return set()
    if isinstance(value, (list, tuple, set)):
        return {str(v) for v in value}
    return {str(value)}


def rules_before_node(node: "Node", source: bytes) -> list[RuleAnnotation]:
    """Collect `@cdec` tags from the comment block directly above `node`.

    Walks previous siblings while they are `comment` nodes on consecutive lines,
    so the block reads like a stack of decorators. Line adjacency is required:
    a comment separated from the declaration by a blank line is prose, not a tag
    (tree-sitter emits no node for blank lines, so sibling order alone can't tell
    the two apart).
    """
    texts: list[str] = []
    expected_line = node.start_point[0] - 1
    current = node.prev_sibling
    while current is not None and current.type == "comment":
        if current.end_point[0] != expected_line:
            break
        texts.append(source[current.start_byte : current.end_byte].decode("utf-8", "replace"))
        expected_line = current.start_point[0] - 1
        current = current.prev_sibling
    # Walked bottom-up; restore source order so stacked tags keep their order.
    texts.reverse()
    return rules_from_comments(texts)


def _parse_args(raw: str) -> tuple[list[str], dict[str, str]]:
    """Split `(a, b = c)` into positional and keyword argument *source text*.

    Values are kept verbatim (quotes and brackets included) to match the
    `RuleAnnotation` contract used by the Python and C# extractors, so consumers
    like `conformance._str_list` and `layer_dependencies._layer_of` read them the
    same way regardless of source language.
    """
    args: list[str] = []
    kwargs: dict[str, str] = {}
    inner = _balanced_inner(raw)
    if not inner.strip():
        return args, kwargs

    for part in _split_top_level(inner):
        part = part.strip()
        if not part:
            continue
        name, sep, value = _split_keyword(part)
        if sep:
            kwargs[name] = value.strip()
        else:
            args.append(part)
    return args, kwargs


def _balanced_inner(raw: str) -> str:
    """Return the contents of the leading balanced `(...)` group in `raw`.

    Stops at the matching close paren so a trailing comment after the annotation
    (`---@cdec layer("domain")  -- the core`) doesn't leak into the arguments.
    """
    raw = raw.lstrip()
    if not raw.startswith("("):
        return ""
    depth = 0
    quote: str | None = None
    for i, ch in enumerate(raw):
        if quote is not None:
            if ch == quote and raw[i - 1 : i] != "\\":
                quote = None
            continue
        if ch in "\"'":
            quote = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
            if depth == 0:
                return raw[1:i]
    # Unbalanced: take everything after the opening paren rather than dropping
    # the tag entirely.
    return raw[1:]


def _split_top_level(inner: str) -> list[str]:
    """Split on commas that are not nested inside brackets or quotes."""
    parts: list[str] = []
    depth = 0
    quote: str | None = None
    start = 0
    for i, ch in enumerate(inner):
        if quote is not None:
            if ch == quote and inner[i - 1 : i] != "\\":
                quote = None
            continue
        if ch in "\"'":
            quote = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append(inner[start:i])
            start = i + 1
    parts.append(inner[start:])
    return parts


def _split_keyword(part: str) -> tuple[str, bool, str]:
    """Split `name = value` at the first top-level `=`.

    Returns `(name, is_keyword, value)`. Comparison operators (`==`, `!=`, `<=`,
    `>=`) are not keyword separators.
    """
    depth = 0
    quote: str | None = None
    for i, ch in enumerate(part):
        if quote is not None:
            if ch == quote and part[i - 1 : i] != "\\":
                quote = None
            continue
        if ch in "\"'":
            quote = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == "=" and depth == 0:
            if part[i + 1 : i + 2] == "=" or part[i - 1 : i] in ("!", "<", ">", "="):
                continue
            name = part[:i].strip()
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
                return name, True, part[i + 1 :]
            return "", False, part
    return "", False, part
