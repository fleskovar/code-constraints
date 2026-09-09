"""One test per human-readable case folder under `tests/cases/`.

Adding a case is adding a folder — this file never changes. See
`tests/cases/README.md` for the layout and `tests/case_runner.py` for how each
engine is invoked.

    make test-cases                                          # all of them
    make test-case CASE=check/subclass-naming/python/...     # one
    UPDATE_BASELINES=1 make test-cases                       # regenerate (review the diff!)
"""

from __future__ import annotations

import pytest

from tests.case_runner import (
    Case,
    discover_cases,
    load_baseline,
    run_case,
    updating,
    write_baseline,
)

CASES = discover_cases()


def _id(case: Case) -> str:
    return case.name


@pytest.mark.parametrize("case", CASES, ids=_id)
def test_case(case: Case) -> None:
    findings = run_case(case)
    if updating():
        write_baseline(case, findings)
        pytest.skip(f"baseline regenerated for {case.name} — review the diff")
    expected = load_baseline(case)
    assert findings == expected, (
        f"\n{case.name} drifted from its baseline.\n"
        f"  expected: {expected}\n"
        f"  actual:   {findings}\n"
        f"Read {case.name}/README.md - the walkthrough derives every expected row "
        f"by hand. A red run is a regression until proven otherwise."
    )


def test_every_case_has_a_readme() -> None:
    """The README *is* the test. A case folder without one is a golden file."""
    missing = [c.name for c in CASES if not (c.root / "README.md").is_file()]
    assert missing == [], f"case folders with no README.md: {missing}"


def test_cases_were_discovered() -> None:
    """Guard against the whole suite silently vanishing behind a bad glob."""
    assert CASES, "no case folders discovered under tests/cases/"
