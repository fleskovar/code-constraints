"""The rule engine's view of the `exceptions:` ledger.

The file itself is owned by `code_constraints.waivers.store`, which is engine-
agnostic; this module is the thin adapter that turns `Violation`s into lookups
against it. Keeping the file format in one place is what lets an exception
granted from a reviewed report and one recorded by
`cdec check --automatic-exceptions` land in the same list.
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
        # Locks are never exempted: `Violation.waivable` is False for them, and
        # honouring an `exceptions:` entry here would be a silent back door
        # around the privileged re-baseline.
        return v.waivable and self.store.has(v.key())

    def filter(
        self, violations: list[Violation]
    ) -> tuple[list[Violation], list[Violation]]:
        kept: list[Violation] = []
        suppressed: list[Violation] = []
        for v in violations:
            (suppressed if self.contains(v) else kept).append(v)
        return kept, suppressed


def load_baseline(config_dir: Path) -> Baseline:
    return Baseline(store=load_waivers(config_dir))


def write_baseline(config_dir: Path, violations: Iterable[Violation]) -> Path:
    """Grandfather `violations` as the accepted set — `--automatic-exceptions`.

    Every engine's exceptions are rewritten together, because the violations
    handed in come from one run of every rule. Non-waivable violations (locks)
    are dropped rather than recorded: accepting one of those is a privileged
    re-baseline, never an exception. Reason / author / date already recorded for
    an issue are carried over, so re-running never erases why something was
    accepted. Returns the file written.
    """
    store = load_waivers(config_dir)
    stamp = now_stamp()
    store.replace_all(
        [
            Waiver(
                engine=v.key_engine,
                rule=v.key_rule or v.rule_id,
                qualified_name=v.qualified_name,
                detail=v.signature or "",
                reason=_existing_reason(store, v),
                added=_existing_added(store, v) or stamp,
                added_by=_existing_actor(store, v),
            )
            for v in violations
            if v.waivable
        ]
    )
    return save_waivers(config_dir, store)


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
