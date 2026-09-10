"""The three rule types that adapt an engine reading the source itself.

`tag-conformance`, `implementation-locks` and `reference-architecture` are what
turned three commands into one. They are unlike the other rules in two ways
worth testing directly: they need `ctx.source`, and their violations key under
the *engine* that produced them rather than under the `rules.yaml` entry — which
is what keeps an exception valid when the entry is renamed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from code_constraints.lint.config import load_project_config, load_rules
from code_constraints.lint.engine import SourceContext, run_checks
from code_constraints.lint.pipeline import parse_source

PY_SHIM = '''
def locked(*args, **kwargs):
    if len(args) == 1 and not kwargs and callable(args[0]):
        return args[0]
    return lambda obj: obj


def sealed(*args, **kwargs):
    if len(args) == 1 and not kwargs and callable(args[0]):
        return args[0]
    return lambda obj: obj


def no_instantiation(*args, **kwargs):
    if len(args) == 1 and not kwargs and callable(args[0]):
        return args[0]
    return lambda obj: obj
'''

BILLING = '''\
from cdec_rules import locked, no_instantiation, sealed


@sealed
class Receipt:
    @locked
    def formatted(self):
        return "receipt"


class Ledger:
    @no_instantiation
    def record(self):
        return Receipt()
'''


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    src = tmp_path / "src"
    src.mkdir()
    (src / "cdec_rules.py").write_text(PY_SHIM, encoding="utf-8")
    (src / "billing.py").write_text(BILLING, encoding="utf-8")
    (tmp_path / ".cdec").mkdir()
    return tmp_path


def _write_rules(project: Path, rules: str) -> None:
    (project / ".cdec" / "rules.yaml").write_text(
        "language: python\nsource: src\n\n" + rules, encoding="utf-8"
    )


def _check(project: Path):
    config_dir = project / ".cdec"
    cfg = load_project_config(config_dir)
    loaded = load_rules(config_dir)
    head = parse_source(cfg.source, cfg.language)
    return run_checks(
        head,
        loaded.rules,
        has_diff=False,
        source_context=SourceContext(
            source=cfg.source,
            language=cfg.language,
            config_dir=config_dir,
            reference_path=cfg.reference_path,
        ),
    )


# ---------------------------------------------------------------------------
# tag-conformance
# ---------------------------------------------------------------------------

TAG_RULE = "rules:\n  - id: tags\n    type: tag-conformance\n    severity: error\n"


def test_tag_conformance_finds_a_body_violation(project):
    _write_rules(project, TAG_RULE)
    report = _check(project)
    assert [v.key_rule for v in report.violations] == ["no-instantiation"]
    assert report.violations[0].qualified_name == "Ledger"


def test_a_conformance_violation_keys_under_its_engine_not_the_entry(project):
    """Rename the `rules.yaml` entry and the key must not move, or every
    exception granted against it would silently expire."""
    _write_rules(project, TAG_RULE)
    before = _check(project).violations[0].key()

    _write_rules(
        project,
        "rules:\n  - id: a-completely-different-name\n"
        "    type: tag-conformance\n    severity: error\n",
    )
    after = _check(project).violations[0].key()
    assert before == after
    assert before.startswith("F-")


def test_the_rules_option_adopts_one_tag_at_a_time(project):
    """Turning a tag on across a mature codebase is a rolling job."""
    _write_rules(
        project,
        "rules:\n  - id: tags\n    type: tag-conformance\n"
        "    severity: error\n    rules: [factory]\n",
    )
    assert _check(project).violations == []


def test_ignore_globs_apply_to_conformance_findings(project):
    _write_rules(
        project,
        TAG_RULE + '    ignore: ["Ledger"]\n',
    )
    assert _check(project).violations == []


def test_severity_carries_through_to_the_violation(project):
    _write_rules(
        project,
        "rules:\n  - id: tags\n    type: tag-conformance\n    severity: warning\n",
    )
    report = _check(project)
    assert report.violations[0].severity.value == "warning"
    from code_constraints.lint.rules.base import Severity

    assert not report.has_failures(Severity.ERROR)
    assert report.has_failures(Severity.WARNING)


def test_a_language_without_tags_is_skipped_not_silently_passed(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.ts").write_text("export class Alpha {}\n", encoding="utf-8")
    (tmp_path / ".cdec").mkdir()
    (tmp_path / ".cdec" / "rules.yaml").write_text(
        "language: typescript\nsource: src\n\n" + TAG_RULE, encoding="utf-8"
    )
    report = _check(tmp_path)
    assert report.violations == []
    assert report.skipped and report.skipped[0][0] == "tags"
    assert "no constraint-tag syntax" in report.skipped[0][1]


# ---------------------------------------------------------------------------
# reference-architecture
# ---------------------------------------------------------------------------

REFERENCE_RULE = (
    "rules:\n  - id: shape\n    type: reference-architecture\n    severity: error\n"
)


def _snapshot(project: Path) -> None:
    from code_constraints.core.model_io import save_model

    cfg = load_project_config(project / ".cdec")
    save_model(parse_source(cfg.source, cfg.language), cfg.reference_path)


def test_a_missing_reference_is_skipped_with_the_way_to_make_one(project):
    _write_rules(project, REFERENCE_RULE)
    report = _check(project)
    assert report.violations == []
    assert "--automatic-exceptions reference" in report.skipped[0][1]


def test_the_reference_rule_passes_on_the_snapshot_it_was_taken_from(project):
    _write_rules(project, REFERENCE_RULE)
    _snapshot(project)
    report = _check(project)
    assert report.violations == []
    assert report.skipped == []


def test_the_reference_rule_catches_what_the_diff_engine_cannot(project):
    """The whole reason this rule exists beside `frozen-members`: the diff engine
    matches members by signature and is blind to a visibility change."""
    _write_rules(
        project,
        REFERENCE_RULE
        + "  - id: members\n    type: frozen-members\n    severity: error\n"
          "    scope: snapshot\n",
    )
    _snapshot(project)
    billing = project / "src" / "billing.py"
    billing.write_text(
        billing.read_text(encoding="utf-8").replace("def record(", "def _record("),
        encoding="utf-8",
    )
    report = _check(project)
    rule_ids = {v.rule_id for v in report.violations}
    assert rule_ids == {"shape"}, "only the reference gate should see this"
    assert report.violations[0].key().startswith("R-")


def test_reference_deviations_can_be_accepted_as_exceptions(project):
    """Unlike locks, a reference deviation is an ordinary decision to record."""
    _write_rules(project, REFERENCE_RULE)
    _snapshot(project)
    (project / "src" / "extra.py").write_text("class Extra:\n    pass\n", encoding="utf-8")
    violation = _check(project).violations[0]
    assert violation.waivable is True


def test_the_categories_option_narrows_what_the_gate_rejects(project):
    _write_rules(
        project,
        REFERENCE_RULE + "    categories: [class-removed]\n",
    )
    _snapshot(project)
    (project / "src" / "extra.py").write_text("class Extra:\n    pass\n", encoding="utf-8")
    assert _check(project).violations == [], "class-added is not in the list"


# ---------------------------------------------------------------------------
# implementation-locks
# ---------------------------------------------------------------------------

LOCK_RULE = (
    "rules:\n  - id: frozen\n    type: implementation-locks\n    severity: error\n"
)


def test_a_lock_violation_is_never_acceptable_as_an_exception(project):
    _write_rules(project, LOCK_RULE)
    violation = _check(project).violations[0]
    assert violation.waivable is False
    assert violation.key().startswith("L-")


def test_an_exception_entry_cannot_smuggle_a_lock_past_the_gate(project):
    """`Baseline.contains` must refuse to honour an `exceptions:` entry for a
    lock, or hand-editing the file would be a silent back door."""
    from code_constraints.lint.baseline import Baseline
    from code_constraints.waivers.store import Waiver, WaiverStore

    _write_rules(project, LOCK_RULE)
    violation = _check(project).violations[0]

    store = WaiverStore()
    store.add(
        Waiver(
            engine="lock",
            rule=violation.key_rule or "",
            qualified_name=violation.qualified_name,
        )
    )
    assert Baseline(store=store).contains(violation) is False
