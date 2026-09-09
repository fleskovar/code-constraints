"""Architectural-rule tag extraction, XMI round-trip, diff, and graph JSON."""

from __future__ import annotations

from pathlib import Path

from code_constraints.core.diff import diff_projects
from code_constraints.core.graph_model import build_class_graph
from code_constraints.core.model import DiffStatus, RuleAnnotation
from code_constraints.core.xmi_reader import read_project
from code_constraints.core.xmi_writer import write_project
from code_constraints.csharp import parse_project as parse_csharp
from code_constraints.python import parse_project as parse_python

PY_FIXTURE = Path(__file__).parent / "fixtures" / "python_rules"
CS_FIXTURE = Path(__file__).parent / "fixtures" / "csharp_rules"


def _find(project, qn):
    return next(c for c in project.iter_classes() if c.qualified_name == qn)


def _rule_names(el):
    return {r.name for r in el.rules}


# ---------- Python extraction ----------

def test_python_class_tags_extracted() -> None:
    p = parse_python(PY_FIXTURE)
    repo = _find(p, "Repository")
    assert _rule_names(repo) == {"layer", "sealed"}
    layer = next(r for r in repo.rules if r.name == "layer")
    assert layer.args == ["'domain'"]


def test_python_operation_tags_with_kwargs() -> None:
    p = parse_python(PY_FIXTURE)
    svc = _find(p, "OrderService")
    collect = next(o for o in svc.operations if o.name == "collect")
    rule = next(r for r in collect.rules if r.name == "no-instantiation")
    assert rule.kwargs == {"allow": "['list']"}


def test_python_untagged_class_has_no_rules() -> None:
    p = parse_python(PY_FIXTURE)
    assert _find(p, "Sneaky").rules == []


def test_python_non_shim_decorator_ignored(tmp_path: Path) -> None:
    # A decorator named like a rule but NOT imported from the shim must be ignored.
    (tmp_path / "m.py").write_text(
        "def sealed(c):\n    return c\n\n@sealed\nclass A:\n    pass\n",
        encoding="utf-8",
    )
    p = parse_python(tmp_path)
    assert _find(p, "A").rules == []


# ---------- C# extraction ----------

def test_csharp_class_and_operation_tags() -> None:
    p = parse_csharp(CS_FIXTURE)
    repo = _find(p, "Shop.Repository")
    assert _rule_names(repo) == {"layer", "sealed"}
    svc = _find(p, "Shop.OrderService")
    collect = next(o for o in svc.operations if o.name == "Collect")
    assert "no-instantiation" in _rule_names(collect)


def test_csharp_without_using_ignores_attributes(tmp_path: Path) -> None:
    (tmp_path / "X.cs").write_text(
        "namespace N { [Sealed] public class A { } }\n", encoding="utf-8"
    )
    p = parse_csharp(tmp_path)
    assert _find(p, "N.A").rules == []


# ---------- XMI round-trip ----------

def test_rules_survive_xmi_roundtrip(tmp_path: Path) -> None:
    p = parse_python(PY_FIXTURE)
    out = tmp_path / "r.xmi"
    write_project(p, out)
    back = read_project(out)
    repo = _find(back, "Repository")
    assert _rule_names(repo) == {"layer", "sealed"}
    svc = _find(back, "OrderService")
    collect = next(o for o in svc.operations if o.name == "collect")
    assert next(r for r in collect.rules if r.name == "no-instantiation").kwargs == {
        "allow": "['list']"
    }


# ---------- diff ----------

def test_removing_a_tag_marks_element_changed() -> None:
    old = parse_python(PY_FIXTURE)
    new = parse_python(PY_FIXTURE)
    # Drop the class-level @sealed from Repository in the "new" snapshot.
    repo_new = _find(new, "Repository")
    repo_new.rules = [r for r in repo_new.rules if r.name != "sealed"]
    merged = diff_projects(old, new)
    assert _find(merged, "Repository").status == DiffStatus.CHANGED


def test_removing_an_operation_tag_marks_operation_changed() -> None:
    old = parse_python(PY_FIXTURE)
    new = parse_python(PY_FIXTURE)
    svc_new = _find(new, "OrderService")
    total = next(o for o in svc_new.operations if o.name == "total")
    total.rules = []
    merged = diff_projects(old, new)
    merged_total = next(
        o for o in _find(merged, "OrderService").operations if o.name == "total"
    )
    assert merged_total.status == DiffStatus.CHANGED


# ---------- graph JSON ----------

def test_graph_json_carries_rules() -> None:
    p = parse_python(PY_FIXTURE)
    graph = build_class_graph(p)
    repo_node = next(n for n in graph["nodes"] if n["qualifiedName"] == "Repository")
    assert {r["name"] for r in repo_node["rules"]} == {"layer", "sealed"}
