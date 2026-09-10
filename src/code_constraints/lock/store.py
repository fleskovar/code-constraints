"""The approved-digest ledger — the `locks:` section of `.cdec/rules.yaml`.

The audit trail for frozen implementations. It is meant to be committed and to
sit behind a CODEOWNERS entry so only leads can approve a re-baseline;
`cdec check --automatic-exceptions locks` refuses to overwrite a drifted digest
without `--force` precisely so the diff on this file is the review artefact.

Shape (in the tool-managed tail of `rules.yaml`, see
`code_constraints.core.rulesdoc`):

    locks:
      - target: orders.Receipt.formatted
        kind: method
        algo: py-ast/1
        digest: 3f9a…
        file: orders/billing.py
        locked_at: "2026-08-02T10:15:00Z"
        locked_by: alice
        reason: agreed receipt formatting

A standalone `.cdec/locks.yaml` was the old home. It is still read when present
(so an existing project keeps working on upgrade) and folded into `rules.yaml`
by `cdec init --migrate`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from code_constraints.core.rulesdoc import RULES_FILENAME, RulesFileError, load_document, write_sections
from code_constraints.lock.model import LockEntry

LOCKS_FILENAME = "locks.yaml"  # legacy standalone ledger
LOCKFILE_VERSION = 1


class LockfileError(ValueError):
    """Raised when the lockfile exists but can't be interpreted."""


def load_locks(config_dir: Path) -> dict[str, LockEntry]:
    """Read the ledger into a target -> entry map.

    Accepts either a `.cdec/` directory (the normal call) or a direct path to a
    YAML file holding a `locks:` list. An absent ledger is an empty one —
    nothing is locked yet — which is not an error.
    """
    rules_file, legacy_file = _ledger_paths(config_dir)
    items: list = []
    path = rules_file
    for candidate in (rules_file, legacy_file):
        if candidate is None or not candidate.is_file():
            continue
        try:
            raw = load_document(candidate)
        except RulesFileError as exc:
            raise LockfileError(str(exc)) from exc
        version = raw.get("version", LOCKFILE_VERSION)
        if not isinstance(version, int) or version > LOCKFILE_VERSION:
            raise LockfileError(
                f"{candidate}: lockfile version {version!r} is newer than this "
                f"code-constraints supports (max {LOCKFILE_VERSION}); upgrade with "
                f"`cdec update`."
            )
        found = raw.get("locks") or []
        if not isinstance(found, list):
            raise LockfileError(f"{candidate}: 'locks' must be a list")
        if found:
            # `rules.yaml` wins outright: once migrated, a leftover locks.yaml
            # must not resurrect entries a lead deliberately released.
            items, path = found, candidate
            break

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


def write_locks(config_dir: Path, entries: Iterable[LockEntry]) -> Path:
    """Write the ledger into `rules.yaml`, sorted so the file diffs cleanly.

    Only the `locks:` section is rewritten — every hand-written rule and comment
    above it is preserved byte for byte. Returns the file written.
    """
    rules_file, _ = _ledger_paths(config_dir)
    write_sections(
        rules_file,
        {"locks": [_entry_to_dict(e) for e in sorted(entries, key=lambda e: e.target)]},
    )
    return rules_file


def _ledger_paths(config_dir: Path) -> tuple[Path, Path | None]:
    """(rules.yaml, legacy locks.yaml) for a `.cdec/` dir.

    Passing a YAML file directly is also honoured — tests and `--lockfile`-style
    overrides point straight at one — in which case there is no legacy fallback.
    """
    if config_dir.suffix in (".yaml", ".yml"):
        return config_dir, None
    return config_dir / RULES_FILENAME, config_dir / LOCKS_FILENAME


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
