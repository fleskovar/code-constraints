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
