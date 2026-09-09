"""Parse XML-style comment tags from source code.

Recognised forms (after the comment prefix is stripped):

    <uml-class />
    <uml-activity name="checkout" granularity="control-flow">
    </uml-activity>
    <uml-sequence name="login" root="Handle">
    </uml-sequence>

The caller provides the comment prefix (e.g. `//` for C#, `#` for Python).
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Literal

TagKind = Literal["uml-class", "uml-activity", "uml-sequence"]
_VALID_KINDS: set[str] = {"uml-class", "uml-activity", "uml-sequence"}


@dataclass
class TagInstance:
    """A matched tag span. `start_line` and `end_line` are 1-indexed; the
    closed range covers the lines between the opening and closing tags
    (inclusive of the lines containing the tags themselves)."""
    kind: TagKind
    name: str
    attributes: dict[str, str] = field(default_factory=dict)
    start_line: int = 0
    end_line: int = 0
    self_closed: bool = False


_TAG_LINE_RE = re.compile(r"<\s*/?\s*uml-[a-zA-Z-]+\b[^>]*?/?\s*>")


def find_tags(source: str, comment_prefix: str) -> list[TagInstance]:
    """Scan `source` (full file text) and return tag spans.

    Unbalanced tags (open without close, or vice versa) are skipped silently;
    the parser is intentionally forgiving so a malformed comment never breaks
    the rest of the diagram generation.
    """
    prefix = comment_prefix.strip()
    open_stack: list[tuple[str, dict[str, str], int]] = []
    result: list[TagInstance] = []

    for lineno, line in enumerate(source.splitlines(), start=1):
        stripped = line.strip()
        if not stripped.startswith(prefix):
            continue
        rest = stripped[len(prefix) :].strip()
        match = _TAG_LINE_RE.search(rest)
        if not match:
            continue
        tag_text = match.group(0)

        if tag_text.startswith("</"):
            kind = _extract_kind(tag_text)
            if kind not in _VALID_KINDS:
                continue
            if open_stack and open_stack[-1][0] == kind:
                opened_kind, attrs, opened_line = open_stack.pop()
                result.append(
                    TagInstance(
                        kind=opened_kind,  # type: ignore[arg-type]
                        name=attrs.get("name", ""),
                        attributes=attrs,
                        start_line=opened_line,
                        end_line=lineno,
                        self_closed=False,
                    )
                )
            continue

        is_self_closing = tag_text.rstrip().endswith("/>")
        # ET requires balanced XML — rewrite an open tag as self-closing so
        # we can reuse it to parse attributes.
        parse_text = tag_text if is_self_closing else tag_text.rstrip()[:-1] + "/>"
        try:
            element = ET.fromstring(parse_text)
        except ET.ParseError:
            continue
        kind = element.tag
        if kind not in _VALID_KINDS:
            continue
        attrs = dict(element.attrib)
        if is_self_closing:
            result.append(
                TagInstance(
                    kind=kind,  # type: ignore[arg-type]
                    name=attrs.get("name", ""),
                    attributes=attrs,
                    start_line=lineno,
                    end_line=lineno,
                    self_closed=True,
                )
            )
        else:
            open_stack.append((kind, attrs, lineno))

    return result


def _extract_kind(tag_text: str) -> str:
    """Pull the bare tag name out of `</uml-activity>` etc."""
    cleaned = tag_text.strip().lstrip("<").rstrip(">").lstrip("/").rstrip("/").strip()
    if " " in cleaned:
        cleaned = cleaned.split(" ", 1)[0]
    return cleaned
