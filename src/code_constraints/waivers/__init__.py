"""Waivers — the review loop that lets an enforced codebase keep evolving.

Rules that only ever say "no" get switched off. The point of this package is the
other half of the loop: a violation is reported with a stable key, a human or an
agent decides it is acceptable, and that decision is recorded in
`.cdec/baseline.yaml` with a reason — reviewable in the diff, and revocable.

    cdec check                          # every issue prints its key
    cdec baseline review --out r.txt    # one line per issue, ready to mark
    …mark lines [ALLOW]…
    cdec baseline patch --file r.txt    # apply exactly those decisions
    cdec baseline allow V-1A2B3C4D      # or name one directly

Locks (Engine C) are pointedly excluded — see `model.NotWaivable`.
"""

from code_constraints.core.keys import (
    KEY_RE,
    engine_of,
    find_keys,
    is_key,
    make_key,
    normalize_key,
)
from code_constraints.waivers.collect import CollectOptions, Collected, collect_issues
from code_constraints.waivers.model import Issue, NotWaivable
from code_constraints.waivers.ops import (
    ApplyResult,
    allow_keys,
    apply_decisions,
    prune,
    remove_keys,
)
from code_constraints.waivers.review import (
    Decision,
    ReviewDecisions,
    parse_review,
    render_issue_line,
    render_review,
)
from code_constraints.waivers.store import (
    WAIVABLE_ENGINES,
    Waiver,
    WaiverFileError,
    WaiverStore,
    default_actor,
    load_waivers,
    now_stamp,
    save_waivers,
)

__all__ = [
    "ApplyResult",
    "CollectOptions",
    "Collected",
    "Decision",
    "Issue",
    "KEY_RE",
    "NotWaivable",
    "ReviewDecisions",
    "WAIVABLE_ENGINES",
    "Waiver",
    "WaiverFileError",
    "WaiverStore",
    "allow_keys",
    "apply_decisions",
    "collect_issues",
    "default_actor",
    "engine_of",
    "find_keys",
    "is_key",
    "load_waivers",
    "make_key",
    "normalize_key",
    "now_stamp",
    "parse_review",
    "prune",
    "remove_keys",
    "render_issue_line",
    "render_review",
    "save_waivers",
]
