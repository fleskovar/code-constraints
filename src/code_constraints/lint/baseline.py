"""Engine A's view of `.cdec/baseline.yaml`.

The file itself is owned by `code_constraints.waivers.store`, which is engine-
agnostic; this module is the thin adapter that turns lint `Violation`s into
lookups against it. Keeping the file format in one place is what lets a waiver
granted from a reviewed report and one recorded by `--update-baseline` land in
the same ledger.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from code_constraints.lint.rules.base import Violation
from code_constraints.waivers.store import (
    Waiver,
    WaiverStore,
    load_waivers,
    now_stamp,
    save_waivers,
)


@dataclass
class Baseline:
    store: WaiverStore = field(default_factory=WaiverStore)

    def contains(self, v: Violation) -> bool:
        return self.store.has(v.key())

    def filter(
        self, violations: list[Violation]
    ) -> tuple[list[Violation], list[Violation]]:
        kept: list[Violation] = []
        suppressed: list[Violation] = []
        for v in violations:
            (suppressed if self.contains(v) else kept).append(v)
        return kept, suppressed


def load_baseline(path: Path) -> Baseline:
    return Baseline(store=load_waivers(path))


def write_baseline(path: Path, violations: Iterable[Violation]) -> None:
    """Record `violations` as the accepted set for Engine A.

    Conformance waivers (Engine B) in the same file are preserved: they were
    granted by a separate decision and re-snapshotting drift must not quietly
    revoke them.
    """
    store = load_waivers(path)
    stamp = now_stamp()
    store.replace_engine(
        "check",
        [
            Waiver(
                engine="check",
                rule=v.rule_id,
                qualified_name=v.qualified_name,
                detail=v.signature or "",
                reason=_existing_reason(store, v),
                added=_existing_added(store, v) or stamp,
                added_by=_existing_actor(store, v),
            )
            for v in violations
        ],
    )
    save_waivers(path, store)


def _existing(store: WaiverStore, v: Violation) -> Waiver | None:
    return store.get(v.key())


def _existing_reason(store: WaiverStore, v: Violation) -> str:
    existing = _existing(store, v)
    return existing.reason if existing else ""


def _existing_added(store: WaiverStore, v: Violation) -> str:
    existing = _existing(store, v)
    return existing.added if existing else ""


def _existing_actor(store: WaiverStore, v: Violation) -> str:
    existing = _existing(store, v)
    return existing.added_by if existing else ""
