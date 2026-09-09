"""Unit tests for the code_constraints.lint rule engine and individual rules."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from code_constraints.core.diff import diff_projects
from code_constraints.core.model import (
    Attribute,
    Class,
    DiffStatus,
    Operation,
    Package,
    Parameter,
    Project,
    RuleAnnotation,
    SourceLocation,
)
from code_constraints.python import parse_project as parse_python

PY_RULES_FIXTURE = Path(__file__).parent / "fixtures" / "python_rules"
from code_constraints.lint.baseline import Baseline, write_baseline, load_baseline
from code_constraints.lint.engine import run_checks
from code_constraints.lint.rules import get_rule_class
from code_constraints.lint.rules.base import Rule, Severity


def _make_rule(type_name: str, *, scope: str = "snapshot", **opts) -> Rule:
    rule_cls = get_rule_class(type_name)
    assert rule_cls is not None, f"unknown rule type {type_name}"
    return rule_cls(
        rule_id=opts.pop("rule_id", type_name),
        severity=Severity(opts.pop("severity", "error")),
        scope=scope,
        message=opts.pop("message", ""),
        ignore=opts.pop("ignore", []),
        options=opts,
    )


def _base_project() -> Project:
    animal = Class(
        name="Animal",
        qualified_name="zoo.Animal",
        attributes=[Attribute(name="name", type="str")],
        operations=[Operation(name="speak", return_type="str")],
        location=SourceLocation(file="animal.py", start_line=1, end_line=10),
    )
    dog = Class(
        name="Dog",
        qualified_name="zoo.Dog",
        bases=["zoo.Animal"],
        attributes=[Attribute(name="breed", type="str")],
        location=SourceLocation(file="dog.py", start_line=1, end_line=8),
    )
    pkg = Package(name="zoo", qualified_name="zoo", classes=[animal, dog])
    return Project(source_language="python", packages=[pkg])


# ---------------- no-new-classes ----------------

def test_no_new_classes_fires_on_added() -> None:
    old = _base_project()
    new = deepcopy(old)
    new.packages[0].classes.append(Class(name="Cat", qualified_name="zoo.Cat"))
    annotated = diff_projects(old, new)
    rule = _make_rule("no-new-classes", scope="diff")
    report = run_checks(annotated, [rule], has_diff=True)
    assert len(report.violations) == 1
    assert report.violations[0].qualified_name == "zoo.Cat"


def test_no_new_classes_silent_when_no_changes() -> None:
    old = _base_project()
    new = deepcopy(old)
    annotated = diff_projects(old, new)
    rule = _make_rule("no-new-classes", scope="diff")
    report = run_checks(annotated, [rule], has_diff=True)
    assert report.violations == []


def test_no_new_classes_respects_ignore() -> None:
    old = _base_project()
    new = deepcopy(old)
    new.packages[0].classes.append(Class(name="Cat", qualified_name="zoo.Cat"))
    annotated = diff_projects(old, new)
    rule = _make_rule("no-new-classes", scope="diff", ignore=["zoo.Cat"])
    report = run_checks(annotated, [rule], has_diff=True)
    assert report.violations == []


def test_no_new_classes_skipped_without_diff() -> None:
    proj = _base_project()
    rule = _make_rule("no-new-classes", scope="diff")
    report = run_checks(proj, [rule], has_diff=False)
    assert report.violations == []
    assert any(rule.rule_id == r[0] for r in report.skipped)


# ---------------- no-removed-classes ----------------

def test_no_removed_classes_fires() -> None:
    old = _base_project()
    new = deepcopy(old)
    new.packages[0].classes = [c for c in new.packages[0].classes if c.name != "Dog"]
    annotated = diff_projects(old, new)
    rule = _make_rule("no-removed-classes", scope="diff")
    report = run_checks(annotated, [rule], has_diff=True)
    assert [v.qualified_name for v in report.violations] == ["zoo.Dog"]


# ---------------- dangling-classes ----------------

def test_dangling_classes_fires_on_orphan() -> None:
    proj = _base_project()
    # Add a class that no one references and isn't referenced.
    proj.packages[0].classes.append(Class(name="Lonely", qualified_name="zoo.Lonely"))
    rule = _make_rule("dangling-classes", scope="snapshot")
    report = run_checks(proj, [rule], has_diff=False)
    qns = {v.qualified_name for v in report.violations}
    assert "zoo.Lonely" in qns


def test_dangling_classes_skips_entry_point() -> None:
    proj = _base_project()
    proj.packages[0].classes.append(Class(name="Main", qualified_name="zoo.Main"))
    rule = _make_rule("dangling-classes", scope="snapshot", entry_points=["*Main*"])
    report = run_checks(proj, [rule], has_diff=False)
    qns = {v.qualified_name for v in report.violations}
    assert "zoo.Main" not in qns


def test_dangling_classes_silenced_by_incoming_ref() -> None:
    proj = _base_project()
    # Dog references Animal via inheritance — Animal has incoming, Dog does not.
    rule = _make_rule("dangling-classes", scope="snapshot")
    report = run_checks(proj, [rule], has_diff=False)
    qns = {v.qualified_name for v in report.violations}
    assert "zoo.Animal" not in qns
    assert "zoo.Dog" in qns


def test_dangling_classes_silenced_by_method_signature_ref() -> None:
    """A class referenced only as a method param / return type is not dangling."""
    proj = _base_project()
    snap = Class(name="Snapshot", qualified_name="zoo.Snapshot")
    viewer = Class(
        name="Viewer",
        qualified_name="zoo.Viewer",
        operations=[
            Operation(
                name="capture",
                parameters=[Parameter(name="s", type="Snapshot")],
                return_type="Snapshot",
            )
        ],
    )
    proj.packages[0].classes.extend([snap, viewer])
    rule = _make_rule("dangling-classes", scope="snapshot")
    report = run_checks(proj, [rule], has_diff=False)
    qns = {v.qualified_name for v in report.violations}
    assert "zoo.Snapshot" not in qns


def test_dangling_classes_silenced_by_body_dependency_ref() -> None:
    """A utility class referenced only inside a method body is not dangling."""
    proj = _base_project()
    util = Class(name="Utils", qualified_name="zoo.Utils")
    caller = Class(
        name="Caller",
        qualified_name="zoo.Caller",
        dependencies=["Utils"],
    )
    proj.packages[0].classes.extend([util, caller])
    rule = _make_rule("dangling-classes", scope="snapshot")
    report = run_checks(proj, [rule], has_diff=False)
    qns = {v.qualified_name for v in report.violations}
    assert "zoo.Utils" not in qns


def test_dangling_classes_skips_framework_subclass() -> None:
    """A MonoBehaviour subclass is a framework entry point, never dangling."""
    proj = _base_project()
    comp = Class(
        name="PlayerView",
        qualified_name="zoo.PlayerView",
        bases=["MonoBehaviour"],
    )
    proj.packages[0].classes.append(comp)
    rule = _make_rule("dangling-classes", scope="snapshot")
    report = run_checks(proj, [rule], has_diff=False)
    qns = {v.qualified_name for v in report.violations}
    assert "zoo.PlayerView" not in qns


# ---------------- frozen-members ----------------

def test_frozen_members_fires_on_added_attribute() -> None:
    old = _base_project()
    new = deepcopy(old)
    new.packages[0].classes[0].attributes.append(Attribute(name="age", type="int"))
    annotated = diff_projects(old, new)
    rule = _make_rule("frozen-members", scope="diff", classes=["zoo.Animal"])
    report = run_checks(annotated, [rule], has_diff=True)
    assert len(report.violations) == 1
    assert report.violations[0].qualified_name == "zoo.Animal"
    assert "age" in (report.violations[0].signature or "")


def test_frozen_members_silent_when_other_class_changes() -> None:
    old = _base_project()
    new = deepcopy(old)
    new.packages[0].classes[1].attributes.append(Attribute(name="age", type="int"))
    annotated = diff_projects(old, new)
    rule = _make_rule("frozen-members", scope="diff", classes=["zoo.Animal"])
    report = run_checks(annotated, [rule], has_diff=True)
    assert report.violations == []


def test_frozen_members_ignore_silences() -> None:
    old = _base_project()
    new = deepcopy(old)
    new.packages[0].classes[0].attributes.append(Attribute(name="age", type="int"))
    annotated = diff_projects(old, new)
    rule = _make_rule(
        "frozen-members", scope="diff", classes=["zoo.Animal"], ignore=["zoo.Animal"]
    )
    report = run_checks(annotated, [rule], has_diff=True)
    assert report.violations == []


# ---------------- forbidden-references ----------------

def test_forbidden_references_fires_on_inheritance() -> None:
    proj = _base_project()
    rule = _make_rule(
        "forbidden-references", scope="snapshot",
        **{"from": ["zoo.Dog"], "to": ["zoo.Animal"]},
    )
    report = run_checks(proj, [rule], has_diff=False)
    assert len(report.violations) == 1
    assert report.violations[0].qualified_name == "zoo.Dog"


def test_forbidden_references_fires_on_attribute_type() -> None:
    proj = _base_project()
    # Add Owner with attribute typed Dog.
    owner = Class(
        name="Owner",
        qualified_name="zoo.Owner",
        attributes=[Attribute(name="pet", type="Dog")],
    )
    proj.packages[0].classes.append(owner)
    rule = _make_rule(
        "forbidden-references", scope="snapshot",
        **{"from": ["zoo.Owner"], "to": ["zoo.Dog"]},
    )
    report = run_checks(proj, [rule], has_diff=False)
    assert {v.qualified_name for v in report.violations} == {"zoo.Owner"}


def test_forbidden_references_ignore() -> None:
    proj = _base_project()
    rule = _make_rule(
        "forbidden-references", scope="snapshot",
        ignore=["zoo.Dog"],
        **{"from": ["zoo.Dog"], "to": ["zoo.Animal"]},
    )
    report = run_checks(proj, [rule], has_diff=False)
    assert report.violations == []


# ---------------- forbidden-package-references ----------------

def test_forbidden_package_references_fires() -> None:
    proj = _base_project()
    # Add a second package that references the first.
    p2 = Package(
        name="ui", qualified_name="ui",
        classes=[Class(
            name="View", qualified_name="ui.View",
            attributes=[Attribute(name="animal", type="zoo.Animal")],
        )],
    )
    proj.packages.append(p2)
    rule = _make_rule(
        "forbidden-package-references", scope="snapshot",
        **{"from": ["ui"], "to": ["zoo"]},
    )
    report = run_checks(proj, [rule], has_diff=False)
    qns = {(v.qualified_name, v.signature) for v in report.violations}
    assert ("ui", "->zoo") in qns


# ---------------- subclass-naming ----------------

def test_subclass_naming_fires_on_misnamed_subclass() -> None:
    proj = Project(
        source_language="python",
        packages=[Package(name="app", qualified_name="app", classes=[
            Class(name="IFactory", qualified_name="app.IFactory", kind="interface"),
            Class(name="WidgetMaker", qualified_name="app.WidgetMaker", bases=["app.IFactory"]),
            Class(name="WidgetFactory", qualified_name="app.WidgetFactory", bases=["app.IFactory"]),
        ])],
    )
    rule = _make_rule(
        "subclass-naming", scope="snapshot",
        base="IFactory", name_pattern=".*Factory$",
    )
    report = run_checks(proj, [rule], has_diff=False)
    assert [v.qualified_name for v in report.violations] == ["app.WidgetMaker"]


# ---------------- cyclic package dependencies ----------------

def test_cyclic_package_dependencies_detects_loop() -> None:
    proj = Project(
        source_language="python",
        packages=[
            Package(name="a", qualified_name="a", classes=[
                Class(name="A", qualified_name="a.A", attributes=[Attribute(name="b", type="b.B")]),
            ]),
            Package(name="b", qualified_name="b", classes=[
                Class(name="B", qualified_name="b.B", attributes=[Attribute(name="a", type="a.A")]),
            ]),
        ],
    )
    rule = _make_rule("no-cyclic-package-dependencies", scope="snapshot")
    report = run_checks(proj, [rule], has_diff=False)
    assert len(report.violations) >= 1


def test_cyclic_package_dependencies_silent_when_acyclic() -> None:
    proj = Project(
        source_language="python",
        packages=[
            Package(name="a", qualified_name="a", classes=[
                Class(name="A", qualified_name="a.A", attributes=[Attribute(name="b", type="b.B")]),
            ]),
            Package(name="b", qualified_name="b", classes=[
                Class(name="B", qualified_name="b.B"),
            ]),
        ],
    )
    rule = _make_rule("no-cyclic-package-dependencies", scope="snapshot")
    report = run_checks(proj, [rule], has_diff=False)
    assert report.violations == []


# ---------------- max-class-fanout ----------------

def test_max_class_fanout_fires_when_over_limit() -> None:
    proj = Project(
        source_language="python",
        packages=[Package(name="a", qualified_name="a", classes=[
            Class(name="A", qualified_name="a.A"),
            Class(name="B", qualified_name="a.B"),
            Class(name="C", qualified_name="a.C"),
            Class(name="Hub", qualified_name="a.Hub", attributes=[
                Attribute(name="a", type="a.A"),
                Attribute(name="b", type="a.B"),
                Attribute(name="c", type="a.C"),
            ]),
        ])],
    )
    rule = _make_rule("max-class-fanout", scope="snapshot", limit=2)
    report = run_checks(proj, [rule], has_diff=False)
    assert [v.qualified_name for v in report.violations] == ["a.Hub"]


# ---------------- baseline ----------------

def test_baseline_silences_known_violations(tmp_path) -> None:
    old = _base_project()
    new = deepcopy(old)
    new.packages[0].classes.append(Class(name="Cat", qualified_name="zoo.Cat"))
    annotated = diff_projects(old, new)
    rule = _make_rule("no-new-classes", scope="diff")
    report = run_checks(annotated, [rule], has_diff=True, baseline=Baseline())
    assert len(report.violations) == 1
    # Record baseline, then re-run.
    path = tmp_path / "baseline.yaml"
    write_baseline(path, report.violations)
    baseline = load_baseline(path)
    report2 = run_checks(annotated, [rule], has_diff=True, baseline=baseline)
    assert report2.violations == []
    assert len(report2.suppressed) == 1


def test_baseline_still_catches_new_violation(tmp_path) -> None:
    old = _base_project()
    new = deepcopy(old)
    new.packages[0].classes.append(Class(name="Cat", qualified_name="zoo.Cat"))
    annotated = diff_projects(old, new)
    rule = _make_rule("no-new-classes", scope="diff")
    initial = run_checks(annotated, [rule], has_diff=True)
    path = tmp_path / "baseline.yaml"
    write_baseline(path, initial.violations)
    baseline = load_baseline(path)
    # Now add a second new class beyond the baseline.
    new2 = deepcopy(new)
    new2.packages[0].classes.append(Class(name="Fish", qualified_name="zoo.Fish"))
    annotated2 = diff_projects(old, new2)
    report = run_checks(annotated2, [rule], has_diff=True, baseline=baseline)
    assert [v.qualified_name for v in report.violations] == ["zoo.Fish"]


# ---------------- custom failure messages ----------------

def test_custom_message_placeholders_are_interpolated() -> None:
    old = _base_project()
    new = deepcopy(old)
    new.packages[0].classes.append(Class(name="Cat", qualified_name="zoo.Cat"))
    annotated = diff_projects(old, new)
    rule = _make_rule(
        "no-new-classes",
        scope="diff",
        message="DENIED: {qualified_name} is a brand-new class.",
    )
    report = run_checks(annotated, [rule], has_diff=True)
    assert len(report.violations) == 1
    assert report.violations[0].message == "DENIED: zoo.Cat is a brand-new class."


def test_multiline_message_is_indented_in_human_report() -> None:
    old = _base_project()
    new = deepcopy(old)
    new.packages[0].classes.append(Class(name="Cat", qualified_name="zoo.Cat"))
    annotated = diff_projects(old, new)
    rule = _make_rule(
        "no-new-classes",
        scope="diff",
        message="{qualified_name} appeared.\nSecond line.\nThird line.",
    )
    report = run_checks(annotated, [rule], has_diff=True)
    text = report.to_human()
    # First line on the bullet (behind the review key), continuation lines
    # indented to align under the message column (not under the leading bullet).
    violation = report.violations[0]
    assert f"  - [{violation.key()}] zoo.Cat: zoo.Cat appeared." in text
    assert "      Second line." in text
    assert "      Third line." in text


def test_forbidden_package_references_message_has_source_and_target() -> None:
    proj = Project(
        source_language="python",
        packages=[
            Package(name="a", qualified_name="a", classes=[
                Class(name="A", qualified_name="a.A", attributes=[Attribute(name="b", type="b.B")]),
            ]),
            Package(name="b", qualified_name="b", classes=[Class(name="B", qualified_name="b.B")]),
        ],
    )
    rule = _make_rule(
        "forbidden-package-references",
        scope="snapshot",
        message="Layering: {source} -> {target} is banned.",
        **{"from": ["a"], "to": ["b"]},
    )
    report = run_checks(proj, [rule], has_diff=False)
    assert any(v.message == "Layering: a -> b is banned." for v in report.violations)


# ---------------- frozen-rules ----------------

def _find_class(proj: Project, qn: str) -> Class:
    return next(c for c in proj.iter_classes() if c.qualified_name == qn)


def test_frozen_rules_fires_when_class_tag_removed() -> None:
    old = parse_python(PY_RULES_FIXTURE)
    new = parse_python(PY_RULES_FIXTURE)
    repo_new = _find_class(new, "Repository")
    repo_new.rules = [r for r in repo_new.rules if r.name != "sealed"]
    annotated = diff_projects(old, new)
    rule = _make_rule("frozen-rules", scope="diff")
    report = run_checks(annotated, [rule], has_diff=True, baseline_project=old)
    assert len(report.violations) == 1
    v = report.violations[0]
    assert v.qualified_name == "Repository"
    assert "@sealed" in (v.signature or "")
    assert "removed" in v.message


def test_frozen_rules_fires_when_operation_tag_weakened() -> None:
    old = parse_python(PY_RULES_FIXTURE)
    new = parse_python(PY_RULES_FIXTURE)
    svc_new = _find_class(new, "OrderService")
    collect = next(o for o in svc_new.operations if o.name == "collect")
    # Weaken: expand the allow-list on the @no_instantiation tag.
    collect.rules = [RuleAnnotation(name="no-instantiation", kwargs={"allow": "['list', 'dict']"})]
    annotated = diff_projects(old, new)
    rule = _make_rule("frozen-rules", scope="diff")
    report = run_checks(annotated, [rule], has_diff=True, baseline_project=old)
    assert len(report.violations) == 1
    v = report.violations[0]
    assert v.qualified_name == "OrderService"
    assert "weakened" in v.message


def test_frozen_rules_silent_when_tags_unchanged() -> None:
    old = parse_python(PY_RULES_FIXTURE)
    new = parse_python(PY_RULES_FIXTURE)
    annotated = diff_projects(old, new)
    rule = _make_rule("frozen-rules", scope="diff")
    report = run_checks(annotated, [rule], has_diff=True, baseline_project=old)
    assert report.violations == []


def test_frozen_rules_allows_adding_a_tag() -> None:
    old = parse_python(PY_RULES_FIXTURE)
    new = parse_python(PY_RULES_FIXTURE)
    # Strengthen Money by adding a sealed tag — adding constraints is allowed.
    _find_class(new, "Money").rules.append(RuleAnnotation(name="sealed"))
    annotated = diff_projects(old, new)
    rule = _make_rule("frozen-rules", scope="diff")
    report = run_checks(annotated, [rule], has_diff=True, baseline_project=old)
    assert report.violations == []


def test_frozen_rules_skipped_without_baseline() -> None:
    proj = parse_python(PY_RULES_FIXTURE)
    rule = _make_rule("frozen-rules", scope="diff")
    report = run_checks(proj, [rule], has_diff=False)
    assert report.violations == []
    assert any(rule.rule_id == r[0] for r in report.skipped)


# ---------------- layer-dependencies ----------------

def _layered_project() -> Project:
    """ui.View -> domain.Service -> data.Repo, each tagged with @layer."""
    view = Class(
        name="View", qualified_name="ui.View",
        attributes=[Attribute(name="svc", type="domain.Service")],
        rules=[RuleAnnotation(name="layer", args=["'ui'"])],
    )
    service = Class(
        name="Service", qualified_name="domain.Service",
        attributes=[Attribute(name="repo", type="data.Repo")],
        rules=[RuleAnnotation(name="layer", args=["'domain'"])],
    )
    repo = Class(
        name="Repo", qualified_name="data.Repo",
        rules=[RuleAnnotation(name="layer", args=["'data'"])],
    )
    return Project(source_language="python", packages=[
        Package(name="ui", qualified_name="ui", classes=[view]),
        Package(name="domain", qualified_name="domain", classes=[service]),
        Package(name="data", qualified_name="data", classes=[repo]),
    ])


def test_layer_dependencies_flags_forbidden_direction() -> None:
    proj = _layered_project()
    # domain may depend on data; data may depend on nothing. Add a back-edge:
    # data.Repo references domain.Service (a forbidden upward dependency).
    repo = _find_class(proj, "data.Repo")
    repo.attributes.append(Attribute(name="svc", type="domain.Service"))
    rule = _make_rule(
        "layer-dependencies", scope="snapshot",
        allow={"ui": ["domain"], "domain": ["data"], "data": []},
    )
    report = run_checks(proj, [rule], has_diff=False)
    assert [v.qualified_name for v in report.violations] == ["data.Repo"]
    assert "data" in report.violations[0].signature
    assert "domain" in report.violations[0].signature


def test_layer_dependencies_allows_permitted_direction() -> None:
    proj = _layered_project()
    rule = _make_rule(
        "layer-dependencies", scope="snapshot",
        allow={"ui": ["domain"], "domain": ["data"], "data": []},
    )
    report = run_checks(proj, [rule], has_diff=False)
    assert report.violations == []


def test_layer_dependencies_ignores_unconstrained_layers() -> None:
    proj = _layered_project()
    # Only constrain 'data'; ui->domain and domain->data are unconstrained.
    rule = _make_rule(
        "layer-dependencies", scope="snapshot",
        allow={"data": []},
    )
    report = run_checks(proj, [rule], has_diff=False)
    assert report.violations == []


# ---------------- severity off ----------------

def test_severity_off_filtered_out_in_config(tmp_path) -> None:
    from code_constraints.lint.config import load_rules

    cfg_dir = tmp_path / ".cdec"
    cfg_dir.mkdir()
    (cfg_dir / "rules.yaml").write_text(
        "rules:\n"
        "  - id: noop\n"
        "    type: no-new-classes\n"
        "    severity: off\n",
        encoding="utf-8",
    )
    loaded = load_rules(cfg_dir)
    assert loaded.rules == []
