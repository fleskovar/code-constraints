"""Stable, human-quotable identifiers for a reported issue.

Every issue that any of the three engines reports carries a *key*: a short
token like ``V-1A2B3C4D`` that identifies the issue and nothing else. The key is
what makes the review workflow work — a human (or an agent) can read a report,
mark a line, and say "allow this one" without describing the violation again.

Two properties matter, and they drive the whole design:

  * **Stable across runs.** Re-running a check over an unchanged tree must
    produce identical keys, so a review file stays valid and an agent can round-
    trip report → decision → `cdec baseline allow`.
  * **Stable across unrelated edits.** The key is derived from the *identity* of
    the issue (engine, rule, qualified name, discriminating detail) and never
    from a file offset or line number. Inserting an import above a class must
    not invalidate a waiver granted for that class.

The flip side of the second property is deliberate: a key names an *equivalence
class* of issues, not a physical line. Two identical violations of one rule on
one element share a key, and waiving it waives both. That is the intended
semantic — the reviewer is accepting a fact about the code, not a coordinate.

The prefix letter records which engine produced the issue, so a key alone is
enough to route it:

    V-  `cdec check`    (Engine A — architectural drift)
    F-  `cdec enforce`  (Engine B — implementation conformance)
    L-  `cdec lock`     (Engine C — implementation freeze)
"""

from __future__ import annotations

import hashlib
import re

# Engine name -> key prefix letter. Engine names match the CLI commands.
ENGINE_PREFIX: dict[str, str] = {
    "check": "V",
    "enforce": "F",
    "lock": "L",
}
PREFIX_ENGINE: dict[str, str] = {v: k for k, v in ENGINE_PREFIX.items()}

# 8 hex chars = 32 bits. At a thousand issues in one report the odds of any
# collision are ~1 in 8500, and a collision only ever merges two issues of the
# same engine into one waiver — annoying, never unsound.
_KEY_HEX_LEN = 8

KEY_RE = re.compile(r"\b([VFL])-([0-9A-F]{%d})\b" % _KEY_HEX_LEN)


class UnknownEngine(ValueError):
    pass


def make_key(engine: str, rule: str, qualified_name: str, detail: str = "") -> str:
    """Compute the stable key for one issue.

    `detail` is the per-engine discriminator that separates two issues of the
    same rule on the same element — the `signature` for a lint violation, an
    explicit detail string for a conformance finding. Pass "" when the rule can
    only fire once per element.
    """
    prefix = ENGINE_PREFIX.get(engine)
    if prefix is None:
        raise UnknownEngine(f"unknown engine: {engine!r}")
    raw = "|".join((engine, rule, qualified_name, detail or ""))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:_KEY_HEX_LEN]
    return f"{prefix}-{digest.upper()}"


def engine_of(key: str) -> str | None:
    """The engine that produced `key`, or None if it isn't a well-formed key."""
    match = KEY_RE.fullmatch(key.strip())
    if match is None:
        return None
    return PREFIX_ENGINE.get(match.group(1))


def is_key(text: str) -> bool:
    return KEY_RE.fullmatch(text.strip()) is not None


def find_keys(text: str) -> list[str]:
    """Every key appearing in `text`, in order, de-duplicated."""
    seen: list[str] = []
    for match in KEY_RE.finditer(text):
        key = match.group(0)
        if key not in seen:
            seen.append(key)
    return seen


def normalize_key(text: str) -> str:
    """Accept a key the way a human might retype it (lowercase hex, missing
    hyphen) and return the canonical form. Returns "" if it isn't a key."""
    candidate = text.strip().upper().replace(" ", "")
    if candidate and "-" not in candidate and len(candidate) == _KEY_HEX_LEN + 1:
        candidate = f"{candidate[0]}-{candidate[1:]}"
    return candidate if is_key(candidate) else ""
