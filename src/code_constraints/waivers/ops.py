"""Apply review decisions to the waiver store.

Kept apart from the CLI so the rules about what may be waived — and what must
be refused — are testable on their own and identical whether the decision
arrives from a marked-up file, a key on the command line, or (later) an MCP
call.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from code_constraints.core.keys import normalize_key
from code_constraints.waivers.collect import Collected
from code_constraints.waivers.model import Issue, NotWaivable
from code_constraints.waivers.review import Decision, ReviewDecisions
from code_constraints.waivers.store import Waiver, WaiverStore, default_actor


@dataclass
class ApplyResult:
    allowed: list[Issue] = field(default_factory=list)
    already_waived: list[Issue] = field(default_factory=list)
    removed: list[Waiver] = field(default_factory=list)
    # Keys that match no current issue and no existing waiver. Nearly always a
    # stale report or a mistyped key, so it's an error rather than a no-op.
    unknown: list[str] = field(default_factory=list)
    # (key, explanation) for issues that exist but must not be waived — locks.
    refused: list[tuple[str, str]] = field(default_factory=list)
    # [REMOVE] on a key that wasn't waived in the first place.
    not_waived: list[str] = field(default_factory=list)
    malformed: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.allowed or self.removed)

    @property
    def failed(self) -> bool:
        return bool(self.unknown or self.refused or self.malformed or self.problems)


def apply_decisions(
    store: WaiverStore,
    collected: Collected,
    decisions: ReviewDecisions,
    *,
    default_reason: str = "",
    actor: str | None = None,
) -> ApplyResult:
    """Apply `[ALLOW]` / `[REMOVE]` decisions to `store` in memory."""
    result = ApplyResult(problems=list(decisions.problems))
    who = default_actor() if actor is None else actor
    index = collected.by_key()

    for decision in decisions.allow:
        _allow_one(store, index, decision, default_reason, who, result)
    for decision in decisions.remove:
        _remove_one(store, decision, result)
    return result


def allow_keys(
    store: WaiverStore,
    collected: Collected,
    keys: Iterable[str],
    *,
    reason: str = "",
    actor: str | None = None,
) -> ApplyResult:
    """Waive issues named directly by key — the agent-friendly path."""
    decisions = ReviewDecisions(allow=[Decision(key=k) for k in keys])
    return apply_decisions(
        store, collected, decisions, default_reason=reason, actor=actor
    )


def remove_keys(store: WaiverStore, keys: Iterable[str]) -> ApplyResult:
    """Withdraw waivers by key. Needs no source parse — the store is enough."""
    result = ApplyResult()
    for raw in keys:
        _remove_one(store, Decision(key=raw), result)
    return result


def prune(store: WaiverStore, collected: Collected) -> list[Waiver]:
    """Drop waivers whose issue no longer occurs, and return them.

    Only prunes engines that actually ran this time round: a waiver is not
    stale just because the engine that would have reported it was skipped.
    """
    engines_ran = collected.engines_ran
    live = {issue.key for issue in collected.issues}
    stale = [
        w for w in store.waivers if w.engine in engines_ran and w.key not in live
    ]
    for waiver in stale:
        store.remove(waiver.key)
    return stale


# ---------- internals ----------

def _allow_one(
    store: WaiverStore,
    index: dict[str, Issue],
    decision: Decision,
    default_reason: str,
    actor: str,
    result: ApplyResult,
) -> None:
    key = normalize_key(decision.key)
    if not key:
        result.malformed.append(decision.key)
        return
    issue = index.get(key)
    if issue is None:
        result.unknown.append(key)
        return
    reason = decision.reason or default_reason
    try:
        waiver = issue.to_waiver(reason=reason, actor=actor)
    except NotWaivable as exc:
        result.refused.append((key, str(exc)))
        return
    if store.add(waiver):
        result.allowed.append(issue)
    else:
        result.already_waived.append(issue)


def _remove_one(store: WaiverStore, decision: Decision, result: ApplyResult) -> None:
    key = normalize_key(decision.key)
    if not key:
        result.malformed.append(decision.key)
        return
    if not store.has(key):
        result.not_waived.append(key)
        return
    waiver = store.remove(key)
    if waiver is not None:
        result.removed.append(waiver)
    else:
        # A hand-written key with no matching tuple: it was honoured for
        # matching, and dropping it is still a real change.
        result.removed.append(
            Waiver(engine="check", rule="(hand-written key)", qualified_name=key)
        )
