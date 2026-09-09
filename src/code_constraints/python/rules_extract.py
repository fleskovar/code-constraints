"""Recognise architectural-rule decorators on Python classes/functions.

Shared by the UML parser (to attach `RuleAnnotation`s to the model) and the
`cdec enforce` conformance analyzer (to find tagged elements). A decorator counts
as a rule only when its base name was imported from one of the shim modules
(`cdec_rules` / `code_constraints.rules`) — so a user's own decorator that happens to
share a name is never misread as a rule.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field

from code_constraints.core.model import RuleAnnotation
from code_constraints.core.rules import PYTHON_SHIM_MODULES, by_python_name


@dataclass
class ImportMap:
    # local name -> exported shim name, for `from <shim> import x [as y]`
    from_imports: dict[str, str] = field(default_factory=dict)
    # local module alias -> real shim module dotted name
    module_aliases: dict[str, str] = field(default_factory=dict)


def build_import_map(tree: ast.AST) -> ImportMap:
    im = ImportMap(module_aliases={m: m for m in PYTHON_SHIM_MODULES})
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod in PYTHON_SHIM_MODULES:
                for alias in node.names:
                    im.from_imports[alias.asname or alias.name] = alias.name
            elif mod == "code_constraints":
                for alias in node.names:
                    if alias.name == "rules":
                        im.module_aliases[alias.asname or "rules"] = "code_constraints.rules"
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in PYTHON_SHIM_MODULES and alias.asname:
                    im.module_aliases[alias.asname] = alias.name
    return im


def extract_rules(decorator_list: list[ast.expr], import_map: ImportMap) -> list[RuleAnnotation]:
    rules: list[RuleAnnotation] = []
    for dec in decorator_list:
        callee = dec.func if isinstance(dec, ast.Call) else dec
        spec_id = _resolve(callee, import_map)
        if spec_id is None:
            continue
        args: list[str] = []
        kwargs: dict[str, str] = {}
        if isinstance(dec, ast.Call):
            args = [_unparse(a) for a in dec.args]
            for kw in dec.keywords:
                if kw.arg is not None:
                    kwargs[kw.arg] = _unparse(kw.value)
        rules.append(RuleAnnotation(name=spec_id, args=args, kwargs=kwargs))
    return rules


def _resolve(callee: ast.expr, im: ImportMap) -> str | None:
    text = _unparse(callee)
    if not text:
        return None
    if "." not in text:
        exported = im.from_imports.get(text)
        spec = by_python_name(exported) if exported else None
    else:
        prefix, _, final = text.rpartition(".")
        spec = by_python_name(final) if prefix in im.module_aliases else None
    return spec.id if spec else None


def _unparse(node: ast.AST | None) -> str:
    if node is None:
        return ""
    try:
        return ast.unparse(node)
    except Exception:
        return ""
