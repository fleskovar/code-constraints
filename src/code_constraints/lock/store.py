"""Load and save `.cdec/locks.yaml` — the approved-digest ledger.

This file is the audit trail for frozen implementations. It is meant to be
committed and to sit behind a CODEOWNERS entry so only leads can approve a
re-baseline; `cdec lock set` refuses to overwrite a drifted digest without
`--force` precisely so the diff on this file is the review artefact.

Shape:

    version: 1
    locks:
      - target: orders.Receipt.formatted
        kind: method
        algo: py-ast/1
        digest: 3f9a…
        file: orders/billing.py
        locked_at: "2026-08-02T10:15:00Z"
        locked_by: alice
        reason: agreed receipt formatting
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import yaml

from code_constraints.lock.model import LockEntry

LOCKS_FILENAME = "locks.yaml"
LOCKFILE_VERSION = 1


class LockfileError(ValueError):
    """Raised when the lockfile exists but can't be interpreted."""


def load_locks(path: Path) -> dict[str, LockEntry]:
    """Read the lockfile into a target -> entry map. A missing file is an empty
    ledger (nothing is locked yet), which is not an error."""
    if not path.is_file():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    if not isinstance(raw, dict):
        raise LockfileError(f"{path}: top-level must be a mapping")
    version = raw.get("version", LOCKFILE_VERSION)
    if not isinstance(version, int) or version > LOCKFILE_VERSION:
        raise LockfileError(
            f"{path}: lockfile version {version!r} is newer than this code-constraints "
            f"supports (max {LOCKFILE_VERSION}); upgrade with `cdec update`."
        )
    items = raw.get("locks") or []
    if not isinstance(items, list):
        raise LockfileError(f"{path}: 'locks' must be a list")

    out: dict[str, LockEntry] = {}
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            raise LockfileError(f"{path}: locks[{i}] must be a mapping")
        target = str(item.get("target") or "")
        digest = str(item.get("digest") or "")
        if not target or not digest:
            raise LockfileError(f"{path}: locks[{i}] needs both 'target' and 'digest'")
        out[target] = LockEntry(
            target=target,
            kind=str(item.get("kind") or "class"),
            digest=digest,
            algo=str(item.get("algo") or ""),
            file=str(item.get("file") or ""),
            locked_at=str(item.get("locked_at") or ""),
            locked_by=str(item.get("locked_by") or ""),
            reason=str(item.get("reason") or ""),
            via_pattern=bool(item.get("via_pattern") or False),
        )
    return out


def write_locks(path: Path, entries: Iterable[LockEntry]) -> None:
    """Write the ledger, sorted by target so the file diffs cleanly."""
    payload = {
        "version": LOCKFILE_VERSION,
        "locks": [_entry_to_dict(e) for e in sorted(entries, key=lambda e: e.target)],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(payload, fh, sort_keys=False, default_flow_style=False)


def now_stamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _entry_to_dict(e: LockEntry) -> dict[str, object]:
    out: dict[str, object] = {
        "target": e.target,
        "kind": e.kind,
        "algo": e.algo,
        "digest": e.digest,
    }
    if e.file:
        out["file"] = e.file
    if e.locked_at:
        out["locked_at"] = e.locked_at
    if e.locked_by:
        out["locked_by"] = e.locked_by
    if e.reason:
        out["reason"] = e.reason
    if e.via_pattern:
        out["via_pattern"] = True
    return out
