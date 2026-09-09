"""Unit tests for the waiver machinery: keys, the ledger, the review file.

The properties under test here are the ones the whole review workflow rests on
— a key that moves when the code is reformatted, or a baseline file that loses
its old entries on upgrade, breaks the loop silently.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from code_constraints.core.keys import (
    engine_of,
    find_keys,
    is_key,
    make_key,
    normalize_key,
)
from code_constraints.enforce.model import Finding
from code_constraints.lint.rules.base import Severity, Violation
from code_constraints.lock.model import LockViolation
from code_constraints.waivers import (
    Issue,
    NotWaivable,
    Waiver,
    WaiverStore,
    load_waivers,
    parse_review,
    render_review,
    save_waivers,
)
from code_constraints.core.model import SourceLocation


# ---------------- keys ----------------

def test_key_is_deterministic() -> None:
    a = make_key("check", "no-new-classes", "zoo.Cat", "")
    b = make_key("check", "no-new-classes", "zoo.Cat", "")
    assert a == b


def test_key_shape_and_engine_prefix() -> None:
    assert is_key(make_key("check", "r", "q"))
    assert engine_of(make_key("check", "r", "q")) == "check"
    assert engine_of(make_key("enforce", "r", "q")) == "enforce"
    assert engine_of(make_key("lock", "changed", "q")) == "lock"
    assert make_key("check", "r", "q").startswith("V-")
    assert make_key("enforce", "r", "q").startswith("F-")
    assert make_key("lock", "r", "q").startswith("L-")


def test_key_separates_engines_rules_elements_and_details() -> None:
    base = make_key("check", "rule", "pkg.Cls", "sig")
    assert base != make_key("enforce", "rule", "pkg.Cls", "sig")
    assert base != make_key("check", "other", "pkg.Cls", "sig")
    assert base != make_key("check", "rule", "pkg.Other", "sig")
    assert base != make_key("check", "rule", "pkg.Cls", "other")


def test_violation_key_ignores_source_location() -> None:
    """The point of the scheme: moving code must not invalidate a waiver."""
    def violation(line: int) -> Violation:
        return Violation(
            rule_id="no-new-classes",
            severity=Severity.ERROR,
            qualified_name="zoo.Cat",
            message="New class 'zoo.Cat' was added.",
            location=SourceLocation(file="zoo/cat.py", start_line=line, end_line=line),
        )

    assert violation(1).key() == violation(120).key()


def test_finding_key_ignores_line_but_not_detail() -> None:
    def finding(line: int, detail: str) -> Finding:
        return Finding(
            rule="no-instantiation",
            qualified_name="app.Svc",
            message="…",
            file="app/svc.py",
            line=line,
            detail=detail,
        )

    assert finding(10, "run->Thing").key() == finding(99, "run->Thing").key()
    assert finding(10, "run->Thing").key() != finding(10, "run->Other").key()


def test_lock_violation_has_a_key() -> None:
    v = LockViolation(kind="changed", target="orders.Receipt.formatted", message="…")
    assert v.key().startswith("L-")


def test_find_keys_extracts_from_a_marked_line() -> None:
    line = "- [ALLOW] [V-1A2B3C4D] [error] [no-new-classes] zoo.Cat: added."
    assert find_keys(line) == ["V-1A2B3C4D"]


def test_find_keys_ignores_lookalikes() -> None:
    assert find_keys("no keys here: V-12345 or X-1A2B3C4D or v-1a2b3c4d") == []


def test_normalize_key_accepts_human_typing() -> None:
    assert normalize_key("v-1a2b3c4d") == "V-1A2B3C4D"
    assert normalize_key(" V1A2B3C4D ") == "V-1A2B3C4D"
    assert normalize_key("nonsense") == ""


# ---------------- store ----------------

def _waiver(rule: str = "no-new-classes", qn: str = "zoo.Cat") -> Waiver:
    return Waiver(engine="check", rule=rule, qualified_name=qn, reason="legacy")


def test_store_roundtrip(tmp_path: Path) -> None:
    store = WaiverStore()
    store.add(_waiver())
    store.add(
        Waiver(
            engine="enforce",
            rule="no-instantiation",
            qualified_name="app.Svc",
            detail="run->Thing",
        )
    )
    path = tmp_path / "baseline.yaml"
    save_waivers(path, store)

    reloaded = load_waivers(path)
    assert reloaded.keys() == store.keys()
    assert reloaded.matches("check", "no-new-classes", "zoo.Cat")
    assert reloaded.matches("enforce", "no-instantiation", "app.Svc", "run->Thing")
    assert not reloaded.matches("enforce", "no-instantiation", "app.Svc", "run->Else")


def test_legacy_baseline_without_keys_still_matches(tmp_path: Path) -> None:
    """A baseline written before keys existed must keep working untouched —
    the key is derived from the tuple, so there is nothing to migrate."""
    path = tmp_path / "baseline.yaml"
    path.write_text(
        "violations:\n"
        "  domain-must-not-depend-on-ui:\n"
        "    - qualified_name: app.domain.Order\n"
        "      signature: '->app.ui.View'\n",
        encoding="utf-8",
    )
    store = load_waivers(path)
    assert store.matches(
        "check", "domain-must-not-depend-on-ui", "app.domain.Order", "->app.ui.View"
    )


def test_hand_written_key_is_honoured(tmp_path: Path) -> None:
    path = tmp_path / "baseline.yaml"
    path.write_text(
        "violations:\n"
        "  some-rule:\n"
        "    - qualified_name: app.A\n"
        "      key: V-DEADBEEF\n",
        encoding="utf-8",
    )
    store = load_waivers(path)
    assert store.has("V-DEADBEEF")


def test_replace_engine_leaves_other_sections_alone(tmp_path: Path) -> None:
    store = WaiverStore()
    store.add(_waiver())
    store.add(Waiver(engine="enforce", rule="sealed", qualified_name="app.Sub"))
    store.replace_engine("check", [_waiver(qn="zoo.Dog")])

    assert store.matches("check", "no-new-classes", "zoo.Dog")
    assert not store.matches("check", "no-new-classes", "zoo.Cat")
    assert store.matches("enforce", "sealed", "app.Sub")


def test_remove_is_reversible(tmp_path: Path) -> None:
    store = WaiverStore()
    waiver = _waiver()
    store.add(waiver)
    assert store.remove(waiver.key) is not None
    assert not store.has(waiver.key)
    assert store.remove(waiver.key) is None


def test_empty_store_writes_a_loadable_file(tmp_path: Path) -> None:
    path = tmp_path / "baseline.yaml"
    save_waivers(path, WaiverStore())
    assert load_waivers(path).waivers == []


# ---------------- review file ----------------

def _issue(engine: str = "check", **kw) -> Issue:
    defaults = dict(
        engine=engine,
        rule="no-new-classes",
        qualified_name="zoo.Cat",
        message="New class 'zoo.Cat' was added.",
        file="zoo/cat.py",
        line=1,
    )
    defaults.update(kw)
    return Issue(**defaults)


def test_render_puts_every_issue_on_one_markable_line() -> None:
    issue = _issue(message="line one\nline two")
    text = render_review([issue])
    body = [ln for ln in text.splitlines() if ln.startswith("- ")]
    assert len(body) == 1
    assert issue.key in body[0]
    # A multi-line message must not spill onto a line the reviewer can't mark.
    assert "line one line two" in body[0]


def test_render_hides_waived_issues_unless_asked() -> None:
    issue = _issue(waived=True)
    assert issue.key not in render_review([issue])
    assert issue.key in render_review([issue], include_waived=True)


def test_parse_review_reads_allow_marks() -> None:
    text = render_review([_issue()])
    marked = text.replace("- [V", "- [ALLOW] [V")
    decisions = parse_review(marked)
    assert [d.key for d in decisions.allow] == [_issue().key]
    assert decisions.remove == []


def test_parse_review_reads_inline_reason() -> None:
    decisions = parse_review("- [ALLOW: legacy, see ARCH-42] [V-1A2B3C4D] whatever")
    assert decisions.allow[0].reason == "legacy, see ARCH-42"


def test_parse_review_reads_remove_marks() -> None:
    for marker in ("[REMOVE]", "[UNALLOW]", "[DENY]"):
        decisions = parse_review(f"- {marker} [V-1A2B3C4D] whatever")
        assert [d.key for d in decisions.remove] == ["V-1A2B3C4D"]


def test_parse_review_ignores_unmarked_and_commented_lines() -> None:
    decisions = parse_review(
        "# - [ALLOW] [V-1A2B3C4D] commented out\n"
        "- [V-2B3C4D5E] not marked\n"
    )
    assert decisions.empty


def test_parse_review_flags_a_mark_with_no_key() -> None:
    decisions = parse_review("- [ALLOW] I meant the one about the cat")
    assert decisions.empty
    assert decisions.problems


def test_parse_review_refuses_a_line_marked_both_ways() -> None:
    decisions = parse_review("- [ALLOW] [REMOVE] [V-1A2B3C4D] x")
    assert decisions.empty
    assert decisions.problems


def test_check_log_output_is_a_valid_patch_file() -> None:
    """`cdec check --log-out` must be markable directly — the review file is a
    convenience, not a required format."""
    from code_constraints.lint.report import Report

    violation = Violation(
        rule_id="no-new-classes",
        severity=Severity.ERROR,
        qualified_name="zoo.Cat",
        message="New class 'zoo.Cat' was added.",
    )
    text = Report(violations=[violation]).to_human()
    marked = text.replace("  - [V", "  - [ALLOW] [V")
    decisions = parse_review(marked)
    assert [d.key for d in decisions.allow] == [violation.key()]


# ---------------- waivability ----------------

def test_lock_issues_refuse_to_become_waivers() -> None:
    issue = _issue(engine="lock", rule="changed", qualified_name="orders.Receipt.formatted")
    assert not issue.waivable
    with pytest.raises(NotWaivable) as exc:
        issue.to_waiver()
    # The refusal has to name the way forward, or the workflow dead-ends here.
    assert "cdec lock set" in str(exc.value)


def test_check_and_enforce_issues_are_waivable() -> None:
    assert _issue("check").waivable
    assert _issue("enforce").waivable
