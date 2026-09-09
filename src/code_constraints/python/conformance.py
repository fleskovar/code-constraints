"""Body-level conformance analysis for Python (`cdec enforce`, Engine B).

Re-parses Python source with `ast` and inspects method bodies for violations of
architectural-rule tags. Reuses the shared recognizer in `rules_extract` so the
set of "what is a rule" stays identical to the UML parser.

Detection is heuristic — there is no type resolution at parse time:
  * `no-instantiation` flags a call whose callee matches a project class or is
    Capitalised (PEP8), unless the type is listed in `allow`.
  * `factory` flags construction of a `creates`-listed type outside its
    designated factory class.
  * `immutable` flags assignment to `self.<field>` outside `__init__`.
The `allow` kwarg is the documented escape hatch for false positives.
"""

from __future__ import annotations

import ast
from pathlib import Path

from code_constraints.core.model import Project
from code_constraints.enforce.model import Finding
from code_constraints.python.rules_extract import ImportMap, build_import_map, extract_rules

CTOR_RULE = "no-instantiation"
FACTORY_RULE = "factory"
IMMUTABLE_RULE = "immutable"


def analyze(root: Path, project: Project) -> list[Finding]:
    qn_by_name = {cls.name: cls.qualified_name for cls in project.iter_classes()}
    project_classes = set(qn_by_name)
    factory_index = _factory_index(project)

    findings: list[Finding] = []
    for py_file in sorted(root.rglob("*.py")):
        try:
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (OSError, SyntaxError):
            continue
        rel = py_file.relative_to(root).as_posix()
        im = build_import_map(tree)
        _analyze_module(
            tree, rel, im, qn_by_name, project_classes, factory_index, findings
        )
    return findings


def _analyze_module(
    tree: ast.Module,
    file: str,
    im: ImportMap,
    qn_by_name: dict[str, str],
    project_classes: set[str],
    factory_index: dict[str, set[str]],
    out: list[Finding],
) -> None:
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            _analyze_class(
                node, file, im, qn_by_name, project_classes, factory_index, out
            )
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            frules = _rule_map(node.decorator_list, im)
            _analyze_function(
                node,
                file=file,
                owner_qn=node.name,
                owner_class_name=None,
                noinst_allow=_allow_set(frules.get(CTOR_RULE)) if CTOR_RULE in frules else None,
                immutable=False,
                project_classes=project_classes,
                factory_index=factory_index,
                out=out,
            )


def _analyze_class(
    cls: ast.ClassDef,
    file: str,
    im: ImportMap,
    qn_by_name: dict[str, str],
    project_classes: set[str],
    factory_index: dict[str, set[str]],
    out: list[Finding],
) -> None:
    crules = _rule_map(cls.decorator_list, im)
    class_qn = qn_by_name.get(cls.name, cls.name)
    class_noinst = _allow_set(crules[CTOR_RULE]) if CTOR_RULE in crules else None
    is_immutable = IMMUTABLE_RULE in crules

    for member in cls.body:
        if not isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        frules = _rule_map(member.decorator_list, im)
        if CTOR_RULE in frules:
            noinst_allow = _allow_set(frules[CTOR_RULE])
        else:
            noinst_allow = class_noinst
        _analyze_function(
            member,
            file=file,
            owner_qn=class_qn,
            owner_class_name=cls.name,
            noinst_allow=noinst_allow,
            immutable=is_immutable,
            project_classes=project_classes,
            factory_index=factory_index,
            out=out,
        )


def _analyze_function(
    func: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    file: str,
    owner_qn: str,
    owner_class_name: str | None,
    noinst_allow: set[str] | None,
    immutable: bool,
    project_classes: set[str],
    factory_index: dict[str, set[str]],
    out: list[Finding],
) -> None:
    for callee, line in _constructions(func):
        is_construction = callee in project_classes or (callee[:1].isupper())
        if noinst_allow is not None and is_construction and callee not in noinst_allow:
            out.append(
                Finding(
                    rule=CTOR_RULE,
                    qualified_name=owner_qn,
                    message=(
                        f"'{owner_qn}.{func.name}' is tagged @no_instantiation but "
                        f"constructs '{callee}'."
                    ),
                    detail=f"{func.name}->{callee}",
                    file=file,
                    line=line,
                )
            )
        designated = factory_index.get(callee)
        if designated is not None and owner_class_name not in designated:
            allowed = ", ".join(sorted(designated)) or "(none)"
            out.append(
                Finding(
                    rule=FACTORY_RULE,
                    qualified_name=owner_qn,
                    message=(
                        f"'{owner_qn}.{func.name}' constructs '{callee}' outside its "
                        f"designated factory ({allowed})."
                    ),
                    detail=f"{func.name}->{callee}",
                    file=file,
                    line=line,
                )
            )

    if immutable and func.name != "__init__":
        for field_name, line in _self_assignments(func):
            out.append(
                Finding(
                    rule=IMMUTABLE_RULE,
                    qualified_name=owner_qn,
                    message=(
                        f"'{owner_qn}' is @immutable but '{func.name}' reassigns field "
                        f"'self.{field_name}' outside __init__."
                    ),
                    detail=f"{func.name}.{field_name}",
                    file=file,
                    line=line,
                )
            )


def _factory_index(project: Project) -> dict[str, set[str]]:
    """Created-type name -> set of class names designated to construct it."""
    idx: dict[str, set[str]] = {}
    for cls in project.iter_classes():
        rule_sources = list(cls.rules) + [r for op in cls.operations for r in op.rules]
        for rule in rule_sources:
            if rule.name != FACTORY_RULE:
                continue
            for created in _str_list(rule.kwargs.get("creates", "")):
                idx.setdefault(created, set()).add(cls.name)
    return idx


def _rule_map(decorator_list, im: ImportMap) -> dict[str, object]:
    return {r.name: r for r in extract_rules(decorator_list, im)}


def _allow_set(rule) -> set[str]:
    if rule is None:
        return set()
    return _str_list(rule.kwargs.get("allow", ""))


def _str_list(source_text: str) -> set[str]:
    """Parse a Python list/tuple literal of strings into a set, e.g.
    "['list', 'dict']" -> {"list", "dict"}. Tolerant: returns {} on anything
    it can't interpret."""
    if not source_text:
        return set()
    try:
        value = ast.literal_eval(source_text)
    except (ValueError, SyntaxError):
        return set()
    if isinstance(value, (list, tuple, set)):
        return {str(v) for v in value}
    return {str(value)}


def _constructions(func) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    for stmt in func.body:
        for node in ast.walk(stmt):
            if isinstance(node, ast.Call):
                name = _callee_name(node.func)
                if name:
                    out.append((name, getattr(node, "lineno", 0)))
    return out


def _callee_name(func: ast.expr) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _self_assignments(func) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    for stmt in func.body:
        for node in ast.walk(stmt):
            targets: list[ast.expr] = []
            if isinstance(node, ast.Assign):
                targets = list(node.targets)
            elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
                targets = [node.target]
            for target in targets:
                if (
                    isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "self"
                ):
                    out.append((target.attr, getattr(node, "lineno", 0)))
    return out
