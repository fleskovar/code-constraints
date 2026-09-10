"""Rule: a frozen implementation may not change at all.

The adapter for the implementation-freeze engine (`code_constraints.lock`,
"Engine C"). It answers a narrower question than every other rule here — not
"did the design drift" or "does the code obey its tag", but "did this body
change at all" — by comparing an AST-derived digest against the approved digest
recorded in the `locks:` section of `.cdec/rules.yaml`.

Two things about this rule are deliberately unlike the others.

**Its violations cannot be excepted.** `waivable=False`, so
`cdec exceptions allow` refuses a lock key and prints the privileged command
instead. Accepting a change to frozen code is
`cdec check --automatic-exceptions locks --force`, which rewrites the ledger and
therefore shows up as a reviewable diff. Route it through the ordinary exception
list and that reviewability is gone.

**It carries its own baseline.** `accept_current_state` records digests for
newly tagged elements — safe for anyone to run, because without `force` it can
only ever *add* a lock, never overwrite evidence that a locked body changed.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Iterable

from code_constraints.core.model import SourceLocation
from code_constraints.lint.rules import register
from code_constraints.lint.rules.base import Rule, RuleContext, RuleSkipped, Violation

if TYPE_CHECKING:
    from code_constraints.lock import LockOptions

#: Languages with an AST fingerprinter. Freezing a body needs one.
LOCKABLE_LANGUAGES = ("python", "csharp", "odin", "lua", "julia")


@register("implementation-locks")
class ImplementationLocks(Rule):
    """Options:
      targets:            list[str] of qualified-name globs to freeze WITHOUT a
                          tag in the source, e.g. ["orders.pricing.**"].
      include_docstrings: bool — do docstring edits count as implementation
                          changes? (default false)
    """

    supports_auto_accept = True

    # ---- configuration ----
    def lock_options(self) -> "LockOptions":
        from code_constraints.lock import LockOptions

        targets = self.options.get("targets") or []
        if not isinstance(targets, list):
            raise RuleSkipped(f"{self.rule_id}: 'targets' must be a list of globs")
        return LockOptions(
            include_docstrings=bool(self.options.get("include_docstrings", False)),
            patterns=[str(t) for t in targets],
        )

    def _resolve(self, ctx: RuleContext) -> tuple[Path, str, Path]:
        """(source, language, config_dir), or `RuleSkipped` explaining why not.

        Returns the values rather than just validating them so the caller — and
        the type checker — both see them narrowed.
        """
        if ctx.source is None or not ctx.language:
            raise RuleSkipped("no source tree resolved")
        if ctx.language not in LOCKABLE_LANGUAGES:
            raise RuleSkipped(
                f"{ctx.language} has no AST fingerprinter; implementation locks "
                f"support {', '.join(LOCKABLE_LANGUAGES)}"
            )
        if ctx.config_dir is None:
            raise RuleSkipped("no .cdec/ folder resolved to read the lock ledger from")
        return ctx.source, ctx.language, ctx.config_dir

    # ---- checking ----
    def check(self, ctx: RuleContext) -> Iterable[Violation]:
        source, language, config_dir = self._resolve(ctx)
        from code_constraints.lock import UnsupportedLockLanguage, check_locks, load_locks

        options = self.lock_options()
        entries = load_locks(config_dir)
        try:
            report = check_locks(source, language, entries, options)
        except UnsupportedLockLanguage as exc:
            raise RuleSkipped(str(exc)) from exc

        for violation in report.violations:
            if self.is_ignored(violation.target):
                continue
            yield Violation(
                rule_id=self.rule_id,
                severity=self.severity,
                qualified_name=violation.target,
                message=self.message_for(
                    qualified_name=violation.target,
                    kind=violation.kind,
                    message=violation.message,
                )
                or violation.message,
                location=(
                    SourceLocation(file=violation.file, start_line=violation.line, end_line=violation.line)
                    if violation.file
                    else None
                ),
                key_engine="lock",
                key_rule=violation.kind,
                waivable=False,
            )

    # ---- baselining ----
    def accept_current_state(self, ctx: RuleContext, *, force: bool = False) -> list[str]:
        """Record digests for locked elements — `--automatic-exceptions locks`.

        Without `force` this only *adds* entries for newly tagged code, so it is
        safe for anyone to run and can never erase the evidence that a frozen
        implementation changed. `force` is the lead-gated path that accepts a
        drifted body and prunes released entries.
        """
        source, language, config_dir = self._resolve(ctx)
        from code_constraints.lock import UnsupportedLockLanguage, load_locks, update_locks, write_locks

        options = self.lock_options()
        entries = load_locks(config_dir)
        try:
            updated, result = update_locks(
                source, language, entries, options, force=force
            )
        except UnsupportedLockLanguage as exc:
            raise RuleSkipped(str(exc)) from exc

        lines: list[str] = []
        for entry in result.added:
            lines.append(f"  + locked   {entry.target}  ({entry.kind}, {entry.digest[:12]})")
        for entry in result.updated:
            lines.append(f"  ~ rebased  {entry.target}  ({entry.kind}, {entry.digest[:12]})")
        for entry in result.removed:
            lines.append(f"  - released {entry.target}")
        for blocked in result.blocked:
            lines.append(
                f"  ! CHANGED  {blocked.target} — left untouched; re-run with --force "
                f"to accept it as the new baseline (a lead's call)."
            )
        for stale in result.stale:
            lines.append(
                f"  ! STALE    {stale.target} — still locked but its element is gone or "
                f"has lost its tag; restore it, or drop it with --force."
            )
        if result.changed:
            lines.append(f"  wrote {len(updated)} lock(s) to {write_locks(config_dir, updated.values())}")
        elif not lines:
            lines.append("  every lock is already recorded; nothing to write.")
        return lines
