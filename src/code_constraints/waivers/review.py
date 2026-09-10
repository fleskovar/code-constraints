"""The review file: render issues for a human, read their decisions back.

This is the round trip the whole feature exists for. `cdec exceptions review`
writes a plain-text report where every issue occupies one line and leads with
its key. A reviewer (or an agent) marks the lines they accept with `[ALLOW]`
and hands the file to `cdec exceptions patch`, which applies exactly those.

The parser is deliberately forgiving, because the file is meant to be edited by
hand and pasted between tools: any line carrying a marker and a key counts, no
matter what else is on it. That means the output of `cdec check --log-out` works
as a patch file too — the review file is a convenience, not a required format.
A `#` at the start of a line comments it out, which is how you cancel a decision
without deleting the evidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

from code_constraints.core.keys import find_keys
from code_constraints.waivers.model import Issue

ALLOW_RE = re.compile(r"\[\s*ALLOW\s*(?::\s*([^\]]*?))?\s*\]", re.IGNORECASE)
REMOVE_RE = re.compile(r"\[\s*(?:REMOVE|UNALLOW|DENY)\s*(?::\s*([^\]]*?))?\s*\]", re.IGNORECASE)

# Order matters: the review file groups by engine in this order, so a reviewer
# reads the cheap decisions before the ones that need a lead.
_ENGINE_HEADINGS: dict[str, str] = {
    "check": "configured architectural rules",
    "enforce": "source-tag conformance — does the implementation obey its tags",
    "reference": "reference-architecture gate — structural deviation",
    "lock": "frozen implementations",
}


@dataclass
class Decision:
    """One marked line in a reviewed file."""

    key: str
    reason: str = ""
    line_no: int = 0
    source_line: str = ""


@dataclass
class ReviewDecisions:
    allow: list[Decision] = field(default_factory=list)
    remove: list[Decision] = field(default_factory=list)
    # Lines that carried a marker but no key — almost always a typo in a key,
    # and silently ignoring them is how a reviewer thinks they allowed
    # something they didn't.
    problems: list[str] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not self.allow and not self.remove


def parse_review(text: str) -> ReviewDecisions:
    """Extract the marked decisions from a reviewed report."""
    out = ReviewDecisions()
    for i, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        allow = ALLOW_RE.search(line)
        remove = REMOVE_RE.search(line)
        if allow is None and remove is None:
            continue
        keys = find_keys(line)
        if not keys:
            marker = "ALLOW" if allow is not None else "REMOVE"
            out.problems.append(
                f"line {i}: [{marker}] with no issue key — nothing to apply: {line}"
            )
            continue
        # A line marked both ways is a mistake worth surfacing rather than
        # resolving by precedence.
        if allow is not None and remove is not None:
            out.problems.append(
                f"line {i}: marked both [ALLOW] and [REMOVE] — skipped: {line}"
            )
            continue
        if allow is not None:
            reason = (allow.group(1) or "").strip()
            bucket = out.allow
        else:
            assert remove is not None  # one of the two matched, checked above
            reason = (remove.group(1) or "").strip()
            bucket = out.remove
        for key in keys:
            bucket.append(Decision(key=key, reason=reason, line_no=i, source_line=line))
    return out


def render_review(issues: Iterable[Issue], *, include_waived: bool = False) -> str:
    """Write the editable report."""
    items = [i for i in issues if include_waived or not i.waived]
    lines = list(_HEADER)
    if not items:
        lines.append("# No issues to review — the project is clean.")
        lines.append("")
        return "\n".join(lines) + "\n"

    for engine in _ENGINE_HEADINGS:
        group = [i for i in items if i.engine == engine]
        if not group:
            continue
        lines.append("")
        heading = _ENGINE_HEADINGS.get(engine, engine)
        lines.append(f"## {heading} — {len(group)} issue(s)")
        if any(not i.waivable for i in group):
            lines.append(
                "## NOT EXCEPTABLE: a frozen implementation changes only via "
                "`cdec check --automatic-exceptions locks --force`."
            )
        lines.append("")
        for issue in sorted(group, key=lambda i: (i.rule, i.qualified_name, i.detail)):
            lines.append(render_issue_line(issue))
    lines.append("")
    return "\n".join(lines) + "\n"


def render_issue_line(issue: Issue) -> str:
    """One issue, one line — the unit the patch parser operates on.

    Everything discriminating goes on this single line (never a continuation),
    because a reviewer marks lines, and a decision must be readable from the
    line it is written on.
    """
    prefix = "- [ACCEPTED] " if issue.waived else "- "
    loc = f" [{issue.location}]" if issue.location else ""
    message = " ".join((issue.message or "").split())
    return (
        f"{prefix}[{issue.key}] [{issue.severity}] [{issue.rule}]{loc} "
        f"{issue.qualified_name}: {message}"
    )


_HEADER = [
    "# cdec review file",
    "#",
    "# One line per issue. To accept an issue as known-and-allowed, add [ALLOW]",
    "# anywhere on its line; add a reason with [ALLOW: why this is acceptable].",
    "# To withdraw an exception already granted, mark the line [REMOVE].",
    "# Lines starting with # are ignored, so commenting one out cancels it.",
    "#",
    "# Then apply the file:",
    "#     cdec exceptions patch --file <this file>",
    "#",
    "# Example:",
    "#     - [ALLOW: legacy, tracked in ARCH-42] [V-1A2B3C4D] [error] [no-new-classes] ...",
]
