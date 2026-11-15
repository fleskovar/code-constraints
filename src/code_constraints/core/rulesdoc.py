"""`.cdec/rules.yaml` — the one file a project commits.

Everything the tool needs to gate a codebase lives here: the project settings,
the rules that are enforced, the exceptions that were granted, and the digests
of frozen implementations. One file, one diff to review, one thing to put behind
CODEOWNERS.

That creates a problem this module exists to solve. The `rules:` section is
hand-written and carries the explanations that make a failed build teach
something; the `exceptions:` and `locks:` sections are written by the tool. A
naive ``yaml.safe_dump`` of the whole document would silently delete every
comment and reflow every ``message: |`` block the first time anyone ran
``cdec check --automatic-exceptions``.

So writes are *surgical*. The tool-written sections live at the end of the file
under a marker line; a write keeps every byte above the marker verbatim and
regenerates only what is below it. Reads are ordinary ``yaml.safe_load`` over
the whole document, so the split is invisible to everything else.

Shape::

    language: python
    source: src

    rules:
      - id: catalog-is-a-leaf
        type: forbidden-package-references
        ...

    # >>> cdec: managed section ...
    exceptions:
      - key: V-1A2B3C4D
        ...
    locks:
      - target: orders.Receipt.formatted
        ...

Deliberately engine-agnostic: this module deals in plain mappings and imports
nothing from `lint`, `enforce`, `lock` or `waivers`, so the engines that write
into the file stay decoupled from each other.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

RULES_FILENAME = "rules.yaml"

#: Top-level keys owned by the tool. Everything else in the file is the user's.
MANAGED_KEYS: tuple[str, ...] = ("exceptions", "locks")

MANAGED_MARKER = (
    "# >>> cdec: managed section — rewritten by `cdec check --automatic-exceptions`\n"
    "# >>> and by `cdec exceptions ...`. Edit the rules above this line, not below it.\n"
)

# A top-level YAML key: no leading whitespace, an identifier, a colon.
_TOP_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*:")


class RulesFileError(ValueError):
    """Raised when `rules.yaml` exists but can't be interpreted."""


def load_document(path: Path) -> dict[str, Any]:
    """Read the whole file as a mapping. A missing file is an empty document."""
    if not path.is_file():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        try:
            raw = yaml.safe_load(fh) or {}
        except yaml.YAMLError as exc:
            raise RulesFileError(f"{path}: not valid YAML ({exc})") from exc
    if not isinstance(raw, dict):
        raise RulesFileError(f"{path}: top-level must be a mapping")
    return raw


def read_section(path: Path, key: str) -> Any:
    """One top-level section, or None when absent."""
    return load_document(path).get(key)


def write_sections(path: Path, sections: dict[str, Any]) -> None:
    """Replace the named tool-owned sections, preserving everything else byte
    for byte.

    Only the keys in `sections` are touched — writing `exceptions` leaves a
    `locks` section exactly as it was, so the two engines can write the same
    file without stepping on each other.
    """
    unknown = set(sections) - set(MANAGED_KEYS)
    if unknown:
        raise RulesFileError(
            f"refusing to write non-managed section(s) {sorted(unknown)} into {path}"
        )

    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    prefix, existing = _split(text)

    merged = dict(existing)
    for key, value in sections.items():
        if value:
            merged[key] = value
        else:
            merged.pop(key, None)

    body = ""
    for key in MANAGED_KEYS:
        if key in merged:
            body += yaml.safe_dump(
                {key: merged[key]}, sort_keys=False, default_flow_style=False,
                allow_unicode=True, width=100000,
            )

    if prefix and not prefix.endswith("\n"):
        prefix += "\n"
    out = prefix
    if body:
        if out and not out.endswith("\n\n"):
            out += "\n"
        out += MANAGED_MARKER + body
    elif not out:
        out = ""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(out, encoding="utf-8")


# ---------- the hand-written `rules:` list ----------
#
# The web app adds a rule and changes a severity. Both edits touch the lines of
# one list entry and keep every other byte, comments included. Each edit is
# checked after the write: the file must parse to exactly the expected list, or
# the original text goes back and the caller gets an error.

class _BlockDumper(yaml.SafeDumper):
    """Writes a multi-line string as a `|` block, so a `message` stays readable."""


_BlockDumper.add_representer(
    str,
    lambda dumper, data: dumper.represent_scalar(
        "tag:yaml.org,2002:str", data, style="|" if "\n" in data else None
    ),
)

_LIST_ITEM_RE = re.compile(r"^(\s*)-\s")


def render_rule(entry: dict[str, Any], indent: str = "  ") -> str:
    """One rule entry as the YAML text of a list item."""
    text = yaml.dump(
        [entry], Dumper=_BlockDumper, sort_keys=False, default_flow_style=False,
        allow_unicode=True, width=100000,
    )
    return "".join(indent + line for line in text.splitlines(keepends=True))


def append_rule(path: Path, entry: dict[str, Any]) -> None:
    """Add `entry` at the end of the `rules:` list of `rules.yaml`."""
    before = load_document(path).get("rules") or []
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True) if path.is_file() else []
    span = _rules_span(lines)
    if span is None:
        # No `rules:` key. Put one above the managed block.
        at = next(
            (start for key, start, _ in _top_level_spans(lines) if key in MANAGED_KEYS),
            len(lines),
        )
        lines[at:at] = ["rules:\n", render_rule(entry), "\n"]
    else:
        key_line, last = span
        if last == key_line:
            # `rules: []` or a bare `rules:`. The list starts here.
            lines[key_line] = "rules:\n"
            added = [render_rule(entry)]
        else:
            match = _LIST_ITEM_RE.match(lines[key_line + 1])
            added = ["\n", render_rule(entry, match.group(1) if match else "  ")]
        if not lines[last].endswith("\n"):
            lines[last] += "\n"
        lines[last + 1:last + 1] = added
    _commit_rules_edit(path, lines, [*before, entry])


def set_rule_severity(path: Path, rule_id: str, severity: str) -> None:
    """Change the `severity:` of one entry of the `rules:` list."""
    if severity not in ("error", "warning", "off"):
        raise RulesFileError(f"severity must be error, warning or off, not {severity!r}")
    before = load_document(path).get("rules") or []
    expected = [
        {**r, "severity": severity} if isinstance(r, dict) and r.get("id") == rule_id else r
        for r in before
    ]
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    start, end, item_indent = _entry_span(path, lines, rule_id)
    key_indent = item_indent + "  "
    # `off` is quoted: YAML 1.1 reads a bare `off` as the boolean False.
    new_line = f"{key_indent}severity: " + ('"off"' if severity == "off" else severity)
    severity_re = re.compile(rf"^{re.escape(key_indent)}severity:[^#]*?(\s+#.*)?$")
    for i in range(start + 1, end):
        match = severity_re.match(lines[i].rstrip("\n"))
        if match:
            lines[i] = new_line + (match.group(1) or "") + "\n"
            break
    else:
        if not lines[start].endswith("\n"):
            lines[start] += "\n"
        lines.insert(start + 1, new_line + "\n")
    _commit_rules_edit(path, lines, expected)


def replace_rule(path: Path, rule_id: str, entry: dict[str, Any]) -> None:
    """Write `entry` in place of the entry `rule_id`. A comment inside the old
    entry goes with it; every line outside the entry stays."""
    before = load_document(path).get("rules") or []
    expected = [entry if isinstance(r, dict) and r.get("id") == rule_id else r for r in before]
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    start, end, item_indent = _entry_span(path, lines, rule_id)
    lines[start:end] = [render_rule(entry, item_indent)]
    _commit_rules_edit(path, lines, expected)


def remove_rule(path: Path, rule_id: str) -> None:
    """Delete the entry `rule_id` from the `rules:` list."""
    before = load_document(path).get("rules") or []
    expected = [r for r in before if not (isinstance(r, dict) and r.get("id") == rule_id)]
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    start, end, _indent = _entry_span(path, lines, rule_id)
    # The blank line after the entry goes with it.
    if end < len(lines) and not lines[end].strip():
        end += 1
    del lines[start:end]
    if not expected:
        span = _rules_span(lines)
        assert span is not None
        lines[span[0]] = "rules: []\n"
    _commit_rules_edit(path, lines, expected)


def _entry_span(path: Path, lines: list[str], rule_id: str) -> tuple[int, int, str]:
    """(first line, line after the last line, indent of the `-`) of one entry.

    The entry must start with `- id: <rule_id>`. Blank lines and comments after
    its last key are not part of it: a comment above the next entry belongs to
    that entry.
    """
    span = _rules_span(lines)
    id_re = re.compile(rf"^(\s*)-\s+id:\s*[\'\"]?{re.escape(rule_id)}[\'\"]?\s*(#.*)?$")
    for start in range(span[0] + 1, span[1] + 1) if span else ():
        match = id_re.match(lines[start].rstrip("\n"))
        if match is None:
            continue
        indent = match.group(1)
        end = next(
            (i for i in range(start + 1, span[1] + 1) if lines[i].startswith(indent + "- ")),  # type: ignore[index]
            span[1] + 1,  # type: ignore[index]
        )
        while end - 1 > start and (
            not lines[end - 1].strip() or lines[end - 1].lstrip().startswith("#")
        ):
            end -= 1
        return start, end, indent
    raise RulesFileError(
        f"{path}: no entry that starts with `- id: {rule_id}`. Edit the file by hand."
    )


def _rules_span(lines: list[str]) -> tuple[int, int] | None:
    """(index of the `rules:` line, index of the last line of its list).

    The span of a top-level key runs to the next key, so it includes trailing
    blank lines and comments. The list ends at its last line that is neither.
    """
    for key, start, end in _top_level_spans(lines):
        if key != "rules":
            continue
        key_line = next(i for i in range(start, end) if _TOP_KEY_RE.match(lines[i]))
        last = key_line
        for i in range(key_line + 1, end):
            stripped = lines[i].strip()
            if stripped and not stripped.startswith("#") and lines[i][:1] in (" ", "\t", "-"):
                last = i
        return key_line, last
    return None


def _commit_rules_edit(path: Path, lines: list[str], expected: list[Any]) -> None:
    original = path.read_text(encoding="utf-8") if path.is_file() else None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(lines), encoding="utf-8")
    try:
        ok = (load_document(path).get("rules") or []) == expected
    except RulesFileError:
        ok = False
    if not ok:
        if original is None:
            path.unlink()
        else:
            path.write_text(original, encoding="utf-8")
        raise RulesFileError(
            f"{path}: the `rules:` list has a layout that cdec cannot edit safely. "
            f"The file is unchanged. Edit it by hand."
        )


# ---------- internals ----------

def _split(text: str) -> tuple[str, dict[str, Any]]:
    """Split the document into (verbatim prefix, parsed managed sections).

    The prefix is everything the user owns. Managed sections are removed from it
    wherever they appear — normally below the marker, but a hand-placed
    `exceptions:` higher up is lifted too, so a write can never produce a
    duplicate top-level key.
    """
    lines = text.splitlines(keepends=True)
    spans = _top_level_spans(lines)

    managed_text = "".join(
        "".join(lines[start:end])
        for key, start, end in spans
        if key in MANAGED_KEYS
    )
    drop: set[int] = set()
    for key, start, end in spans:
        if key in MANAGED_KEYS:
            drop.update(range(start, end))

    prefix_lines = [line for i, line in enumerate(lines) if i not in drop]
    prefix = "".join(prefix_lines)
    # The marker only describes the block below it; without one it is noise.
    prefix = prefix.replace(MANAGED_MARKER, "")
    for marker_line in MANAGED_MARKER.splitlines(keepends=True):
        prefix = prefix.replace(marker_line, "")
    prefix = prefix.rstrip("\n")
    if prefix:
        prefix += "\n"

    if not managed_text.strip():
        return prefix, {}
    try:
        parsed = yaml.safe_load(managed_text) or {}
    except yaml.YAMLError:
        # Unparseable managed text is regenerated from scratch rather than
        # merged; the caller is handing us the authoritative content anyway.
        return prefix, {}
    return prefix, parsed if isinstance(parsed, dict) else {}


def _top_level_spans(lines: list[str]) -> list[tuple[str, int, int]]:
    """(key, start_index, end_index) for every top-level mapping key.

    A span runs from the key line to just before the next top-level key (or
    EOF), so it carries the key's whole nested block. Comment lines immediately
    above a key belong to that key, so they travel with it.
    """
    starts: list[tuple[str, int]] = []
    for i, line in enumerate(lines):
        match = _TOP_KEY_RE.match(line)
        if match is None:
            continue
        starts.append((match.group(1), _comment_block_start(lines, i)))

    spans: list[tuple[str, int, int]] = []
    for pos, (key, start) in enumerate(starts):
        end = starts[pos + 1][1] if pos + 1 < len(starts) else len(lines)
        spans.append((key, start, end))
    return spans


def _comment_block_start(lines: list[str], key_index: int) -> int:
    """Index of the first line of the comment block attached to `key_index`."""
    i = key_index
    while i > 0:
        previous = lines[i - 1].strip()
        if previous.startswith("#"):
            i -= 1
            continue
        break
    return i
