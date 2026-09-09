"""Ledger semantics for `cdec lock` (Engine C).

Covers the five violation kinds, the glob-based locking path, and the privilege
boundary: `cdec lock set` may add locks freely but may only *re-baseline* a
drifted implementation with `force=True`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from code_constraints.lock import (
    LockOptions,
    UnsupportedLockLanguage,
    check_locks,
    load_locks,
    update_locks,
    write_locks,
)

PY_SHIM = '''
def locked(*args, **kwargs):
    if len(args) == 1 and not kwargs and callable(args[0]):
        return args[0]
    return lambda obj: obj
'''

BILLING = '''\
from cdec_rules import locked


class Invoice:
    @locked(reason="agreed settlement order")
    def settle(self, amount):
        tax = amount * 0.2
        return amount + tax

    def describe(self):
        return "invoice"
'''


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    root = tmp_path / "src"
    root.mkdir()
    (root / "cdec_rules.py").write_text(PY_SHIM, encoding="utf-8")
    (root / "billing.py").write_text(BILLING, encoding="utf-8")
    return root


def _baseline(root: Path, options: LockOptions | None = None) -> dict:
    entries, _ = update_locks(root, "python", {}, options)
    return entries


def _kinds(report) -> list[str]:
    return sorted(v.kind for v in report.violations)


def _edit(root: Path, old: str, new: str) -> None:
    path = root / "billing.py"
    text = path.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not in source"
    path.write_text(text.replace(old, new), encoding="utf-8")


# ---------- baseline + clean check ----------

def test_set_records_only_tagged_elements(project):
    entries = _baseline(project)
    assert set(entries) == {"Invoice.settle"}
    entry = entries["Invoice.settle"]
    assert entry.kind == "method"
    assert entry.reason == "agreed settlement order"
    assert entry.algo == "py-ast/1"
    assert entry.via_pattern is False


def test_clean_project_passes(project):
    report = check_locks(project, "python", _baseline(project))
    assert report.ok
    assert report.violations == []
    assert report.checked == 1
    assert report.declared == 1


def test_unrelated_edits_do_not_trip_the_lock(project):
    """Editing a sibling method and inserting code above must leave the lock
    alone — the property that makes AST identity worth the complexity."""
    entries = _baseline(project)
    _edit(project, 'return "invoice"', 'return "an invoice"')
    _edit(project, "class Invoice:", "HEADER = 1\n\n\nclass Invoice:")
    report = check_locks(project, "python", entries)
    assert report.ok, [v.message for v in report.violations]


# ---------- the five violation kinds ----------

def test_changed_body_is_reported(project):
    entries = _baseline(project)
    _edit(project, "amount * 0.2", "amount * 0.3")
    report = check_locks(project, "python", entries)
    assert _kinds(report) == ["changed"]
    v = report.violations[0]
    assert v.target == "Invoice.settle"
    assert v.file == "billing.py"
    assert "agreed settlement order" in v.message
    assert not report.ok


def test_deleting_a_locked_element_is_reported(project):
    entries = _baseline(project)
    _edit(
        project,
        '    @locked(reason="agreed settlement order")\n'
        "    def settle(self, amount):\n"
        "        tax = amount * 0.2\n"
        "        return amount + tax\n\n",
        "",
    )
    report = check_locks(project, "python", entries)
    assert _kinds(report) == ["removed"]
    assert "no longer exists" in report.violations[0].message


def test_deleting_the_tag_does_not_unlock(project):
    """The escape hatch a junior would reach for first: drop the decorator."""
    entries = _baseline(project)
    _edit(project, '    @locked(reason="agreed settlement order")\n', "")
    report = check_locks(project, "python", entries)
    assert _kinds(report) == ["unlocked"]
    assert "does not remove the lock" in report.violations[0].message


def test_tagged_but_not_baselined_is_reported(project):
    """A lock nobody baselined verifies nothing, so it must not pass silently."""
    report = check_locks(project, "python", {})
    assert _kinds(report) == ["missing"]
    assert report.violations[0].target == "Invoice.settle"


def test_algorithm_change_is_distinguished_from_tampering(project):
    entries = _baseline(project)
    entries["Invoice.settle"].algo = "py-ast/0"
    report = check_locks(project, "python", entries)
    assert _kinds(report) == ["algo-mismatch"]
    assert "not comparable" in report.violations[0].message


def test_changed_and_unlocked_do_not_double_report(project):
    """A body edit that also drops the tag is one violation, not two — the
    `changed` finding already tells the whole story."""
    entries = _baseline(project)
    _edit(project, '    @locked(reason="agreed settlement order")\n', "")
    _edit(project, "amount * 0.2", "amount * 0.3")
    report = check_locks(project, "python", entries)
    assert _kinds(report) == ["changed"]


# ---------- glob-driven locks ----------

def test_glob_targets_lock_without_a_tag(project):
    """The route for freezing test logic wholesale, where decorating every
    element would be impractical."""
    options = LockOptions(patterns=["Invoice.*"])
    entries = _baseline(project, options)
    assert set(entries) == {"Invoice.settle", "Invoice.describe"}
    assert entries["Invoice.describe"].via_pattern is True

    _edit(project, 'return "invoice"', 'return "changed"')
    report = check_locks(project, "python", entries, options)
    assert _kinds(report) == ["changed"]
    assert report.violations[0].target == "Invoice.describe"


def test_glob_locked_entries_are_exempt_from_the_tag_check(project):
    """A glob-locked element has no tag to remove, so it must never be reported
    as `unlocked`."""
    options = LockOptions(patterns=["Invoice.describe"])
    entries = _baseline(project, options)
    report = check_locks(project, "python", entries, options)
    assert report.ok


# ---------- privilege boundary ----------

def test_set_will_not_silently_rebaseline_drift(project):
    entries = _baseline(project)
    _edit(project, "amount * 0.2", "amount * 0.3")

    updated, result = update_locks(project, "python", entries)
    assert result.updated == []
    assert [v.target for v in result.blocked] == ["Invoice.settle"]
    assert updated["Invoice.settle"].digest == entries["Invoice.settle"].digest


def test_force_rebaselines_drift(project):
    entries = _baseline(project)
    before = entries["Invoice.settle"].digest
    _edit(project, "amount * 0.2", "amount * 0.3")

    updated, result = update_locks(
        project, "python", entries, force=True, reason="rate change approved"
    )
    assert result.blocked == []
    assert [e.target for e in result.updated] == ["Invoice.settle"]
    assert updated["Invoice.settle"].digest != before
    assert updated["Invoice.settle"].reason == "rate change approved"
    assert check_locks(project, "python", updated).ok


def test_set_without_force_cannot_prune_a_lock(project):
    """Otherwise unlocking would be: delete the tag, re-run `cdec lock set`."""
    entries = _baseline(project)
    _edit(project, '    @locked(reason="agreed settlement order")\n', "")

    updated, result = update_locks(project, "python", entries)
    assert result.removed == []
    assert "Invoice.settle" in updated
    # The run must say so rather than reporting "nothing to do" — otherwise a
    # tampered tree looks clean at the point someone is most likely to look.
    assert [e.target for e in result.stale] == ["Invoice.settle"]
    assert result.clean is False
    assert _kinds(check_locks(project, "python", updated)) == ["unlocked"]


def test_force_prunes_a_released_lock(project):
    entries = _baseline(project)
    _edit(project, '    @locked(reason="agreed settlement order")\n', "")

    updated, result = update_locks(project, "python", entries, force=True)
    assert [e.target for e in result.removed] == ["Invoice.settle"]
    assert updated == {}
    assert check_locks(project, "python", updated).ok


def test_only_restricts_the_scope_of_an_update(project):
    options = LockOptions(patterns=["Invoice.*"])
    entries = _baseline(project, options)
    _edit(project, "amount * 0.2", "amount * 0.3")
    _edit(project, 'return "invoice"', 'return "changed"')

    updated, result = update_locks(
        project, "python", entries, options, only=["Invoice.settle"], force=True
    )
    assert [e.target for e in result.updated] == ["Invoice.settle"]
    assert _kinds(check_locks(project, "python", updated, options)) == ["changed"]


# ---------- bypass ----------

def test_bypass_reports_but_does_not_fail(project):
    entries = _baseline(project)
    _edit(project, "amount * 0.2", "amount * 0.3")

    report = check_locks(
        project, "python", entries, bypass=True, bypass_reason="hotfix #42"
    )
    assert report.ok
    assert report.bypassed is True
    assert report.violations, "violations must still be collected for the audit trail"
    assert report.bypass_reason == "hotfix #42"


def test_bypass_via_environment(project, monkeypatch):
    entries = _baseline(project)
    _edit(project, "amount * 0.2", "amount * 0.3")
    monkeypatch.setenv("CDEC_LOCK_BYPASS", "1")
    monkeypatch.setenv("CDEC_LOCK_BYPASS_REASON", "CI escape hatch")

    report = check_locks(project, "python", entries)
    assert report.ok and report.bypassed
    assert report.bypass_reason == "CI escape hatch"


# ---------- store ----------

def test_ledger_roundtrips(project, tmp_path):
    entries = _baseline(project)
    path = tmp_path / ".cdec" / "locks.yaml"
    write_locks(path, entries.values())
    reloaded = load_locks(path)
    assert reloaded == entries


def test_missing_ledger_is_an_empty_ledger(tmp_path):
    assert load_locks(tmp_path / "nope.yaml") == {}


def test_unsupported_language_is_explicit(project):
    # TypeScript has a UML parser but no fingerprinter, so locks must refuse it
    # by name rather than silently reporting "nothing locked".
    with pytest.raises(UnsupportedLockLanguage, match="csharp, odin, lua and julia"):
        check_locks(project, "typescript", {})
