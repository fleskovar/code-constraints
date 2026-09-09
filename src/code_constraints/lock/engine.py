"""Orchestration for `cdec lock` — the implementation-freeze engine (Engine C).

Two operations, both driven off the same collected fingerprints:

  * `check_locks`  — verify every ledger entry still matches the source.
  * `update_locks` — (re-)record digests; the lead-gated re-baseline path.

Locks are declared two ways, and both are honoured:

  * a `@locked` / `[Locked]` tag on the element — the primary, in-code route;
  * `lock.targets:` globs in `.cdec/config.yaml` — for freezing code that isn't
    practical to decorate, e.g. an entire test package.

The engine never consults the diff, the reference XMI, or the baseline: a lock
is an absolute statement about the current source, not a drift signal.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

from code_constraints.lock.model import (
    LOCK_RULE,
    LockEntry,
    LockReport,
    LockTarget,
    LockViolation,
    match_any_glob,
)
from code_constraints.lock.store import now_stamp

BYPASS_ENV = "CDEC_LOCK_BYPASS"
BYPASS_REASON_ENV = "CDEC_LOCK_BYPASS_REASON"


class UnsupportedLockLanguage(ValueError):
    """Raised for a language with no fingerprinter."""


@dataclass
class LockOptions:
    include_docstrings: bool = False
    patterns: list[str] = field(default_factory=list)


@dataclass
class UpdateResult:
    added: list[LockEntry] = field(default_factory=list)
    updated: list[LockEntry] = field(default_factory=list)
    removed: list[LockEntry] = field(default_factory=list)
    unchanged: int = 0
    # Entries whose digest drifted but that `--force` was not given for.
    blocked: list[LockViolation] = field(default_factory=list)
    # Entries still in the ledger whose element is gone or has lost its tag, and
    # which were left in place because `--force` was not given. Reporting these
    # matters: without them an unforced run over a tampered-with tree would
    # cheerfully print "nothing to do" while the lock is being violated.
    stale: list[LockEntry] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.added or self.updated or self.removed)

    @property
    def clean(self) -> bool:
        return not self.blocked and not self.stale


def collect_targets(
    root: str | Path, lang: str, options: LockOptions | None = None
) -> list[LockTarget]:
    """Fingerprint every lockable element under `root`."""
    opts = options or LockOptions()
    if lang == "python":
        from code_constraints.python.fingerprint import collect_lockables
    elif lang == "csharp":
        from code_constraints.csharp.fingerprint import collect_lockables
    elif lang == "odin":
        from code_constraints.odin.fingerprint import collect_lockables
    elif lang == "lua":
        from code_constraints.lua.fingerprint import collect_lockables
    elif lang == "julia":
        from code_constraints.julia.fingerprint import collect_lockables
    else:
        raise UnsupportedLockLanguage(
            f"`cdec lock` supports python, csharp, odin, lua and julia; got {lang!r}. "
            f"Implementation freezing needs an AST fingerprinter for the language."
        )
    return collect_lockables(root, include_docstrings=opts.include_docstrings)


def is_locked_target(target: LockTarget, patterns: Sequence[str]) -> bool:
    """A target is under lock when it carries the tag or matches a config glob."""
    return target.declared or match_any_glob(target.target, patterns)


def check_locks(
    root: str | Path,
    lang: str,
    entries: dict[str, LockEntry],
    options: LockOptions | None = None,
    *,
    bypass: bool = False,
    bypass_reason: str = "",
) -> LockReport:
    """Verify the ledger against the current source.

    Five failure modes, all of them real ways a frozen implementation stops
    being frozen:

      * `changed`       — the digest moved: the body was edited.
      * `missing`       — tagged `@locked` but never baselined, so nothing is
                          actually being verified.
      * `removed`       — the element is gone (deleting it is a mutation too).
      * `unlocked`      — the element survives but the tag was deleted; without
                          this check, escaping a lock is a one-line edit.
      * `algo-mismatch` — the digest was produced by a different algorithm
                          version, so the comparison is meaningless. Reported
                          separately so an upgrade never looks like tampering.
    """
    opts = options or LockOptions()
    env_bypass, env_reason = _env_bypass()
    bypass = bypass or env_bypass
    bypass_reason = bypass_reason or env_reason

    targets = collect_targets(root, lang, opts)
    by_name = {t.target: t for t in targets}
    violations: list[LockViolation] = []

    for name, entry in sorted(entries.items()):
        target = by_name.get(name)
        if target is None:
            violations.append(
                LockViolation(
                    kind="removed",
                    target=name,
                    file=entry.file,
                    message=(
                        f"'{name}' is locked in the ledger but no longer exists in the "
                        f"source. Deleting or renaming a frozen element is a change: "
                        f"restore it, or have a lead drop the lock with "
                        f"`cdec lock remove --target {name}`."
                        + (f"\nLock reason: {entry.reason}" if entry.reason else "")
                    ),
                    reason=entry.reason,
                    owner=entry.locked_by,
                )
            )
            continue

        if entry.algo and target.algo != entry.algo:
            violations.append(
                LockViolation(
                    kind="algo-mismatch",
                    target=name,
                    file=target.file,
                    line=target.line,
                    expected=entry.algo,
                    actual=target.algo,
                    message=(
                        f"'{name}' was baselined with digest algorithm "
                        f"'{entry.algo}' but this code-constraints computes "
                        f"'{target.algo}'. The digests are not comparable — "
                        f"re-baseline with `cdec lock set --force` after "
                        f"confirming the implementation is unchanged."
                    ),
                )
            )
            continue

        if target.digest != entry.digest:
            violations.append(
                LockViolation(
                    kind="changed",
                    target=name,
                    file=target.file,
                    line=target.line,
                    expected=entry.digest,
                    actual=target.digest,
                    message=_changed_message(name, entry, target),
                    reason=entry.reason or target.reason,
                    owner=entry.locked_by or target.owner,
                )
            )
            continue

        if not entry.via_pattern and not is_locked_target(target, opts.patterns):
            violations.append(
                LockViolation(
                    kind="unlocked",
                    target=name,
                    file=target.file,
                    line=target.line,
                    message=(
                        f"'{name}' is recorded in the lock ledger but its @{LOCK_RULE} "
                        f"tag is gone. Removing the tag does not remove the lock — "
                        f"restore it, or have a lead run "
                        f"`cdec lock remove --target {name}`."
                    ),
                    reason=entry.reason,
                    owner=entry.locked_by,
                )
            )

    declared = 0
    for target in targets:
        if not is_locked_target(target, opts.patterns):
            continue
        declared += 1
        if target.target in entries:
            continue
        violations.append(
            LockViolation(
                kind="missing",
                target=target.target,
                file=target.file,
                line=target.line,
                actual=target.digest,
                message=(
                    f"'{target.target}' is tagged @{LOCK_RULE} but has no baseline "
                    f"digest, so nothing is being verified. Record it with "
                    f"`cdec lock set`."
                ),
                reason=target.reason,
                owner=target.owner,
            )
        )

    return LockReport(
        violations=violations,
        checked=len(entries),
        declared=declared,
        bypassed=bypass,
        bypass_reason=bypass_reason,
    )


def update_locks(
    root: str | Path,
    lang: str,
    entries: dict[str, LockEntry],
    options: LockOptions | None = None,
    *,
    only: Sequence[str] = (),
    force: bool = False,
    prune: bool = True,
    reason: str = "",
    owner: str = "",
) -> tuple[dict[str, LockEntry], UpdateResult]:
    """Recompute digests and return the new ledger plus a summary of changes.

    Adding a lock is cheap; *re-baselining a drifted one is the privileged
    operation*, so an existing entry whose digest moved is only rewritten with
    `force=True`. That keeps `cdec lock set` safe to run by anyone — without
    `--force` it can never erase evidence of a change — while the `--force` run
    shows up as a reviewable diff on `.cdec/locks.yaml`.

    `only` restricts the operation to matching targets (globs). `prune` drops
    ledger entries whose element no longer exists or is no longer locked.
    """
    opts = options or LockOptions()
    targets = collect_targets(root, lang, opts)
    by_name = {t.target: t for t in targets}
    result = UpdateResult()
    out = dict(entries)
    stamp = now_stamp()
    who = owner or _default_owner()

    for target in targets:
        if not is_locked_target(target, opts.patterns):
            continue
        if only and not match_any_glob(target.target, only):
            continue
        existing = out.get(target.target)
        via_pattern = not target.declared
        if existing is None:
            entry = _entry_for(target, stamp, who, reason, via_pattern)
            out[target.target] = entry
            result.added.append(entry)
        elif existing.digest == target.digest and existing.algo == target.algo:
            result.unchanged += 1
        elif force:
            entry = _entry_for(
                target, stamp, who, reason or existing.reason, via_pattern
            )
            out[target.target] = entry
            result.updated.append(entry)
        else:
            result.blocked.append(
                LockViolation(
                    kind="changed",
                    target=target.target,
                    file=target.file,
                    line=target.line,
                    expected=existing.digest,
                    actual=target.digest,
                    message=(
                        f"'{target.target}' has drifted from its baseline. Re-baselining "
                        f"a frozen implementation requires --force (and a lead's "
                        f"approval on the `.cdec/locks.yaml` diff)."
                    ),
                    reason=existing.reason,
                    owner=existing.locked_by,
                )
            )

    for name, entry in list(out.items()):
        if only and not match_any_glob(name, only):
            continue
        target = by_name.get(name)
        if target is not None and is_locked_target(target, opts.patterns):
            continue
        # The element is gone or its tag was deleted. Dropping the ledger entry
        # is privileged: an unforced run leaves it in place so `cdec lock check`
        # keeps reporting it, rather than letting anyone unlock by deleting a
        # decorator and re-running `cdec lock set`.
        if prune and force:
            del out[name]
            result.removed.append(entry)
        else:
            result.stale.append(entry)

    return out, result


def resolve_entries_for_removal(
    entries: dict[str, LockEntry], patterns: Sequence[str]
) -> list[LockEntry]:
    return [e for name, e in sorted(entries.items()) if match_any_glob(name, patterns)]


# ---------- internals ----------

def _entry_for(
    target: LockTarget, stamp: str, who: str, reason: str, via_pattern: bool
) -> LockEntry:
    return LockEntry(
        target=target.target,
        kind=target.kind,
        digest=target.digest,
        algo=target.algo,
        file=target.file,
        locked_at=stamp,
        locked_by=who,
        reason=reason or target.reason,
        via_pattern=via_pattern,
    )


def _changed_message(name: str, entry: LockEntry, target: LockTarget) -> str:
    lines = [
        f"'{name}' is a frozen {entry.kind or target.kind} and its implementation "
        f"changed.",
    ]
    if entry.reason:
        lines.append(f"Lock reason: {entry.reason}")
    if entry.locked_by:
        lines.append(f"Locked by: {entry.locked_by}" + (f" on {entry.locked_at}" if entry.locked_at else ""))
    lines.append(
        "Revert the change, or ask a lead to approve a re-baseline with "
        f"`cdec lock set --target {name} --force`."
    )
    return "\n".join(lines)


def _env_bypass() -> tuple[bool, str]:
    raw = os.environ.get(BYPASS_ENV, "").strip().lower()
    enabled = raw in ("1", "true", "yes", "on")
    return enabled, os.environ.get(BYPASS_REASON_ENV, "").strip() if enabled else ""


def _default_owner() -> str:
    for var in ("CDEC_LOCK_OWNER", "GIT_AUTHOR_NAME", "USERNAME", "USER"):
        value = os.environ.get(var, "").strip()
        if value:
            return value
    return ""


def iter_locked(targets: Iterable[LockTarget], patterns: Sequence[str]):
    for target in targets:
        if is_locked_target(target, patterns):
            yield target
