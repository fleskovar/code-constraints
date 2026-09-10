"""The accepted-issue ledger — the `exceptions:` section of `.cdec/rules.yaml`.

An *exception* is a recorded decision that one known issue is allowed to stay.
It lives next to the rule it exempts, in the same committed file, because that
is the diff a reviewer reads: the law and the exceptions granted against it,
together.

Shape (in the tool-managed tail of `rules.yaml`, see
`code_constraints.core.rulesdoc`):

    exceptions:
      - key: V-1A2B3C4D
        engine: check                 # configured rules
        rule: domain-must-not-depend-on-ui
        qualified_name: app.domain.Order
        detail: "->app.ui.View"
        reason: legacy, tracked in ARCH-42
        added: "2026-08-04T09:00:00+00:00"
        added_by: fran
      - key: F-9E8D7C6B
        engine: enforce               # source-tag conformance
        rule: no-instantiation
        qualified_name: app.billing.Ledger
        detail: "settle->Invoice"

`.cdec/baseline.yaml` was the old home, with a rule-keyed map per engine
(`violations:` / `findings:`). Both that file and that shape still load — the
key is derived from the tuple, so nothing needs rewriting — and
`cdec init --migrate` folds them into `rules.yaml`.

Deliberately engine-agnostic: this module deals in plain strings and never
imports `lint`, `enforce`, or `lock`, so the engines stay decoupled and each one
adapts its own result type at the boundary.

Locks have no place here on purpose. Accepting a changed frozen implementation
is `cdec check --automatic-exceptions locks --force` — a privileged, separately
reviewed act — and routing it through an exception would quietly undo that.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from code_constraints.core.keys import make_key
from code_constraints.core.rulesdoc import (
    RULES_FILENAME,
    RulesFileError,
    load_document,
    write_sections,
)

BASELINE_FILENAME = "baseline.yaml"  # legacy standalone ledger
EXCEPTIONS_SECTION = "exceptions"

#: Engines whose issues may be accepted as exceptions. `lock` is absent by
#: design — see the module docstring.
WAIVABLE_ENGINES: tuple[str, ...] = ("check", "enforce", "reference")

# Legacy nested sections: engine -> (yaml key, name of the detail field there).
_LEGACY_SECTIONS: dict[str, tuple[str, str]] = {
    "check": ("violations", "signature"),
    "enforce": ("findings", "detail"),
}


class WaiverFileError(ValueError):
    """Raised when the ledger exists but can't be interpreted."""


@dataclass(frozen=True)
class Waiver:
    """One accepted issue."""

    engine: str  # "check" | "enforce" | "reference"
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
    """The in-memory form of the `exceptions:` list, indexed by review key."""

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
        if engine not in WAIVABLE_ENGINES:
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
        """Swap every exception for one engine, leaving the others alone.

        Grandfathering re-writes an engine's set wholesale; it must not silently
        discard exceptions granted separately against a different engine.
        """
        kept = [w for w in self.waivers if w.engine != engine]
        self.waivers = kept + list(waivers)

    def replace_all(self, waivers: Iterable[Waiver]) -> None:
        """Swap the whole set — `--automatic-exceptions rules` accepts the
        current state of every engine that ran, so it rewrites all of it."""
        self.waivers = list(waivers)


# ---------- I/O ----------

def ledger_paths(config_dir: Path) -> tuple[Path, Path | None]:
    """(rules.yaml, legacy baseline.yaml) for a `.cdec/` dir.

    A YAML file passed directly is honoured as-is, with no legacy fallback.
    """
    if config_dir.suffix in (".yaml", ".yml"):
        return config_dir, None
    return config_dir / RULES_FILENAME, config_dir / BASELINE_FILENAME


def load_waivers(config_dir: Path) -> WaiverStore:
    """Read the ledger. An absent one is an empty store, not an error.

    Both the current flat `exceptions:` list and the legacy per-engine maps are
    accepted, from `rules.yaml` or from a leftover `baseline.yaml`, so an
    un-migrated project loses nothing.
    """
    rules_file, legacy_file = ledger_paths(config_dir)
    store = WaiverStore()
    for path in (rules_file, legacy_file):
        if path is None or not path.is_file():
            continue
        try:
            raw = load_document(path)
        except RulesFileError as exc:
            raise WaiverFileError(str(exc)) from exc
        _load_flat(store, raw.get(EXCEPTIONS_SECTION), path)
        _load_legacy(store, raw)
    return store


def _load_flat(store: WaiverStore, entries: Any, path: Path) -> None:
    if entries is None:
        return
    if not isinstance(entries, list):
        raise WaiverFileError(f"{path}: '{EXCEPTIONS_SECTION}' must be a list")
    for i, item in enumerate(entries):
        if not isinstance(item, dict):
            raise WaiverFileError(f"{path}: {EXCEPTIONS_SECTION}[{i}] must be a mapping")
        engine = str(item.get("engine") or "check")
        waiver = Waiver(
            engine=engine,
            rule=str(item.get("rule") or ""),
            qualified_name=str(item.get("qualified_name", "")),
            detail=str(item.get("detail", "") or ""),
            reason=str(item.get("reason", "") or ""),
            added=str(item.get("added", "") or ""),
            added_by=str(item.get("added_by", "") or ""),
        )
        store.add(waiver)
        _honour_recorded_key(store, item, waiver)


def _load_legacy(store: WaiverStore, raw: dict[str, Any]) -> None:
    """The pre-unification shape: one rule-keyed map per engine."""
    for engine, (section, detail_field) in _LEGACY_SECTIONS.items():
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
                _honour_recorded_key(store, item, waiver)


def _honour_recorded_key(store: WaiverStore, item: dict[str, Any], waiver: Waiver) -> None:
    """A file written by an older release has no `key:` at all — the canonical
    key is derived from the tuple, so old ledgers keep working with no
    migration. A key that *is* present but disagrees was hand-written; honour it
    rather than silently ignoring the edit."""
    recorded = str(item.get("key", "") or "").strip().upper()
    if recorded and recorded != waiver.key:
        store.extra_keys.add(recorded)


def save_waivers(config_dir: Path, store: WaiverStore) -> Path:
    """Write the `exceptions:` section, sorted so the file diffs cleanly.

    Only that section is rewritten — every hand-written rule and comment above
    it survives byte for byte. Returns the file written.
    """
    rules_file, _ = ledger_paths(config_dir)
    payload: list[dict[str, str]] = []
    for w in sorted(
        store.waivers, key=lambda w: (w.engine, w.rule, w.qualified_name, w.detail)
    ):
        item: dict[str, str] = {
            "key": w.key,
            "engine": w.engine,
            "rule": w.rule,
            "qualified_name": w.qualified_name,
        }
        if w.detail:
            item["detail"] = w.detail
        if w.reason:
            item["reason"] = w.reason
        if w.added:
            item["added"] = w.added
        if w.added_by:
            item["added_by"] = w.added_by
        payload.append(item)
    write_sections(rules_file, {EXCEPTIONS_SECTION: payload})
    return rules_file


def now_stamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def default_actor() -> str:
    """Best-effort identity for the person granting an exception."""
    import os

    for var in ("CDEC_ACTOR", "GIT_AUTHOR_NAME", "USERNAME", "USER"):
        value = os.environ.get(var, "").strip()
        if value:
            return value
    return ""
