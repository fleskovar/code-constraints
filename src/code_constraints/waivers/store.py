"""Read and write `.cdec/baseline.yaml` — the accepted-violations ledger.

A *waiver* is a recorded decision that one known issue is allowed to stay. The
file is the audit trail for that decision: it is meant to be committed, and a
waiver carries the reason, the date, and who granted it so a reviewer reading
the diff can see what was accepted and why.

Shape (the `violations:` section is the historical format and still loads
unchanged; `findings:` is the conformance-engine counterpart):

    violations:                       # Engine A — `cdec check`
      domain-must-not-depend-on-ui:
        - qualified_name: app.domain.Order
          signature: "->app.ui.View"
          key: V-1A2B3C4D
          reason: legacy, tracked in ARCH-42
          added: "2026-08-04T09:00:00+00:00"
          added_by: fran
    findings:                         # Engine B — `cdec enforce`
      no-instantiation:
        - qualified_name: app.billing.Ledger
          detail: "settle->Invoice"
          key: F-9E8D7C6B

Deliberately engine-agnostic: this module deals in plain strings and never
imports `lint`, `enforce`, or `lock`, so the three engines stay decoupled and
each one adapts its own result type at the boundary.

Engine C (`cdec lock`) has no section here on purpose. Accepting a changed
frozen implementation is `cdec lock set --force` — a privileged, separately
reviewed act — and routing it through a waiver file would quietly undo that.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import yaml

from code_constraints.core.keys import make_key

# engine name -> (yaml section, name of the detail field in that section)
_SECTIONS: dict[str, tuple[str, str]] = {
    "check": ("violations", "signature"),
    "enforce": ("findings", "detail"),
}
WAIVABLE_ENGINES = tuple(_SECTIONS)


class WaiverFileError(ValueError):
    """Raised when the baseline file exists but can't be interpreted."""


@dataclass(frozen=True)
class Waiver:
    """One accepted issue."""

    engine: str  # "check" | "enforce"
    rule: str
    qualified_name: str
    detail: str = ""
    reason: str = ""
    added: str = ""
    added_by: str = ""

    @property
    def key(self) -> str:
        return make_key(self.engine, self.rule, self.qualified_name, self.detail)

    def with_metadata(self, reason: str, actor: str) -> "Waiver":
        return Waiver(
            engine=self.engine,
            rule=self.rule,
            qualified_name=self.qualified_name,
            detail=self.detail,
            reason=reason or self.reason,
            added=self.added or now_stamp(),
            added_by=actor or self.added_by,
        )


@dataclass
class WaiverStore:
    """The in-memory form of `baseline.yaml`, indexed by review key."""

    waivers: list[Waiver] = field(default_factory=list)
    # Keys read verbatim from the file that don't agree with the tuple they sit
    # next to (hand-edited entry). Honoured for matching so a hand-written key
    # still silences its issue, but never written back out.
    extra_keys: set[str] = field(default_factory=set)

    # ---- queries ----
    def keys(self) -> set[str]:
        return {w.key for w in self.waivers} | self.extra_keys

    def has(self, key: str) -> bool:
        return key in self.keys()

    def get(self, key: str) -> Waiver | None:
        for w in self.waivers:
            if w.key == key:
                return w
        return None

    def matches(self, engine: str, rule: str, qualified_name: str, detail: str = "") -> bool:
        """True when an issue with this identity is already accepted."""
        if engine not in _SECTIONS:
            return False
        return self.has(make_key(engine, rule, qualified_name, detail))

    def for_engine(self, engine: str) -> list[Waiver]:
        return [w for w in self.waivers if w.engine == engine]

    # ---- mutation ----
    def add(self, waiver: Waiver) -> bool:
        """Record a waiver. Returns False when it was already present."""
        if self.get(waiver.key) is not None:
            return False
        self.waivers.append(waiver)
        self.extra_keys.discard(waiver.key)
        return True

    def remove(self, key: str) -> Waiver | None:
        """Drop the waiver with this key. Returns it, or None if absent."""
        for i, w in enumerate(self.waivers):
            if w.key == key:
                self.extra_keys.discard(key)
                return self.waivers.pop(i)
        if key in self.extra_keys:
            self.extra_keys.discard(key)
            return None
        return None

    def replace_engine(self, engine: str, waivers: Iterable[Waiver]) -> None:
        """Swap every waiver for one engine, leaving the other sections alone.

        `cdec check --update-baseline` rewrites the drift section wholesale; it
        must not silently discard conformance waivers granted separately.
        """
        kept = [w for w in self.waivers if w.engine != engine]
        self.waivers = kept + list(waivers)


# ---------- I/O ----------

def load_waivers(path: Path) -> WaiverStore:
    """Read a baseline file. A missing file is an empty store, not an error."""
    if not path.is_file():
        return WaiverStore()
    with path.open("r", encoding="utf-8") as fh:
        try:
            raw = yaml.safe_load(fh) or {}
        except yaml.YAMLError as exc:
            raise WaiverFileError(f"{path}: not valid YAML ({exc})") from exc
    if not isinstance(raw, dict):
        raise WaiverFileError(f"{path}: top-level must be a mapping")

    store = WaiverStore()
    for engine, (section, detail_field) in _SECTIONS.items():
        entries = raw.get(section) or {}
        if not isinstance(entries, dict):
            continue
        for rule, items in entries.items():
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                waiver = Waiver(
                    engine=engine,
                    rule=str(rule),
                    qualified_name=str(item.get("qualified_name", "")),
                    detail=str(item.get(detail_field, "") or ""),
                    reason=str(item.get("reason", "") or ""),
                    added=str(item.get("added", "") or ""),
                    added_by=str(item.get("added_by", "") or ""),
                )
                store.add(waiver)
                # A pre-existing file has no `key:` at all — the canonical key
                # is derived from the tuple, so old baselines keep working with
                # no migration. A key that *is* present but disagrees was hand-
                # written; honour it rather than silently ignoring the edit.
                recorded = str(item.get("key", "") or "").strip().upper()
                if recorded and recorded != waiver.key:
                    store.extra_keys.add(recorded)
    return store


def save_waivers(path: Path, store: WaiverStore) -> None:
    """Write the ledger, sorted so the file diffs cleanly."""
    payload: dict[str, dict[str, list[dict[str, str]]]] = {}
    for engine, (section, detail_field) in _SECTIONS.items():
        grouped: dict[str, list[dict[str, str]]] = {}
        for w in store.for_engine(engine):
            item: dict[str, str] = {"qualified_name": w.qualified_name}
            if w.detail:
                item[detail_field] = w.detail
            item["key"] = w.key
            if w.reason:
                item["reason"] = w.reason
            if w.added:
                item["added"] = w.added
            if w.added_by:
                item["added_by"] = w.added_by
            grouped.setdefault(w.rule, []).append(item)
        for rule in grouped:
            grouped[rule].sort(
                key=lambda d: (d.get("qualified_name", ""), d.get(detail_field, ""))
            )
        # `violations:` is always emitted (even empty) so the file keeps the
        # shape `cdec init` scaffolds; `findings:` only appears once used.
        if grouped or engine == "check":
            payload[section] = dict(sorted(grouped.items()))

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(payload, fh, sort_keys=False, default_flow_style=False)


def now_stamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def default_actor() -> str:
    """Best-effort identity for the person granting a waiver."""
    import os

    for var in ("CDEC_ACTOR", "GIT_AUTHOR_NAME", "USERNAME", "USER"):
        value = os.environ.get(var, "").strip()
        if value:
            return value
    return ""
