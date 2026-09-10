"""The implementation-freeze engine (Engine C).

Freezes the *body* of a class or function so it cannot change without an
explicit, reviewable re-baseline. Identity is AST-derived, not line-based, so
code added above a locked element never trips it.

Driven by the `implementation-locks` rule type in `.cdec/rules.yaml`, which is
what `cdec check` runs. This package stays independent of the other engines:
the rule is a thin adapter over the entry points below.

Public surface:

    from code_constraints.lock import (
        LockOptions, check_locks, update_locks, collect_targets,
        load_locks, write_locks, format_report,
    )
"""

from code_constraints.lock.engine import (
    BYPASS_ENV,
    BYPASS_REASON_ENV,
    LockOptions,
    UnsupportedLockLanguage,
    UpdateResult,
    check_locks,
    collect_targets,
    is_locked_target,
    resolve_entries_for_removal,
    update_locks,
)
from code_constraints.lock.model import (
    LOCK_RULE,
    LockEntry,
    LockReport,
    LockTarget,
    LockViolation,
    format_report,
    match_any_glob,
    report_to_json,
)
from code_constraints.lock.store import (
    LOCKFILE_VERSION,
    LOCKS_FILENAME,
    LockfileError,
    load_locks,
    write_locks,
)

__all__ = [
    "BYPASS_ENV",
    "BYPASS_REASON_ENV",
    "LOCKFILE_VERSION",
    "LOCKS_FILENAME",
    "LOCK_RULE",
    "LockEntry",
    "LockOptions",
    "LockReport",
    "LockTarget",
    "LockViolation",
    "LockfileError",
    "UnsupportedLockLanguage",
    "UpdateResult",
    "check_locks",
    "collect_targets",
    "format_report",
    "is_locked_target",
    "load_locks",
    "match_any_glob",
    "report_to_json",
    "resolve_entries_for_removal",
    "update_locks",
    "write_locks",
]
