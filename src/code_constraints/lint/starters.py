"""A starter entry for every rule type — the rule gallery of the web app.

Each starter is a complete, valid `rules.yaml` entry that a person adapts. The
values with a `myapp` prefix are placeholders. `tests/test_journey.py` builds
every entry, and fails when a rule type has no starter.

`group` orders the gallery. `needs_reference` marks the types that compare the
code against `.cdec/reference.xmi`: with a snapshot as the reference they
report only what changes after today, which makes them safe to turn on first.
"""

from __future__ import annotations

from typing import Any

from code_constraints.lint.rules import get_rule_class

GROUPS = (
    ("dependencies", "Dependencies", "Which parts of the code may use which other parts."),
    ("change", "Change control", "What may change after the reference model was set."),
    ("shape", "Shape", "Limits on the form of a class."),
    ("source", "Code tags and locks", "Checks that read the source code, not only the model."),
)

_STARTERS: list[dict[str, Any]] = [
    {
        "type": "forbidden-package-references",
        "group": "dependencies",
        "title": "A package must not use another package",
        "summary": "Fails when a class in the `from` packages references a class in the `to` packages.",
        "entry": {
            "id": "domain-does-not-use-ui",
            "type": "forbidden-package-references",
            "severity": "error",
            "from": ["myapp.domain.**"],
            "to": ["myapp.ui.**"],
            "message": "'{source}' must not depend on '{target}'.\n"
                       "Move the reference to the package that owns the workflow.\n",
        },
    },
    {
        "type": "forbidden-references",
        "group": "dependencies",
        "title": "A class must not use another class",
        "summary": "The same check at class level: `from` and `to` are class name globs.",
        "entry": {
            "id": "views-do-not-use-repositories",
            "type": "forbidden-references",
            "severity": "error",
            "from": ["myapp.ui.*View"],
            "to": ["myapp.data.*Repository"],
        },
    },
    {
        "type": "layer-dependencies",
        "group": "dependencies",
        "title": "Layers",
        "summary": "Reads the `@layer` tags in the code. A layer may reference only the layers that `allow` lists for it.",
        "entry": {
            "id": "layering",
            "type": "layer-dependencies",
            "severity": "error",
            "allow": {"ui": ["domain"], "domain": ["data"], "data": []},
        },
    },
    {
        "type": "no-cyclic-package-dependencies",
        "group": "dependencies",
        "title": "No dependency cycles between packages",
        "summary": "Fails when packages depend on each other in a cycle. It has no options.",
        "entry": {
            "id": "no-package-cycles",
            "type": "no-cyclic-package-dependencies",
            "severity": "error",
        },
    },
    {
        "type": "no-new-classes",
        "group": "change",
        "title": "No class outside the reference model",
        "summary": "Fails for a class that is in the code and not in the reference. With a target model as the reference, the code can grow only what the plan contains.",
        "entry": {
            "id": "no-unplanned-classes",
            "type": "no-new-classes",
            "severity": "error",
            "ignore": ["tests.**"],
            "message": "'{qualified_name}' is not in the reference model.\n"
                       "Add it to the plan first, then set the plan as the reference.\n",
        },
    },
    {
        "type": "no-removed-classes",
        "group": "change",
        "title": "No class of the reference model may disappear",
        "summary": "Fails for a class that is in the reference and not in the code.",
        "entry": {"id": "no-removed-classes", "type": "no-removed-classes", "severity": "warning"},
    },
    {
        "type": "new-class-constraints",
        "group": "change",
        "title": "A new class must extend an approved base",
        "summary": "Checks only the classes that are not in the reference. Old code stays as it is.",
        "entry": {
            "id": "new-classes-extend-a-base",
            "type": "new-class-constraints",
            "severity": "error",
            "bases": ["myapp.domain.Entity"],
        },
    },
    {
        "type": "frozen-members",
        "group": "change",
        "title": "Freeze the members of a class",
        "summary": "Fails when an attribute or an operation of the named classes is added or removed.",
        "entry": {
            "id": "public-contract-is-frozen",
            "type": "frozen-members",
            "severity": "error",
            "classes": ["myapp.api.**"],
            "kinds": ["operation"],
        },
    },
    {
        "type": "frozen-rules",
        "group": "change",
        "title": "Freeze the constraint tags",
        "summary": "Fails when a tag that the reference model carries is removed from the code or made weaker.",
        "entry": {"id": "agreed-tags", "type": "frozen-rules", "severity": "error"},
    },
    {
        "type": "reference-architecture",
        "group": "change",
        "title": "The code must match the reference model exactly",
        "summary": "The strictest gate: any structural difference from the reference fails. Use it when the architecture is stable.",
        "entry": {
            "id": "matches-the-reference",
            "type": "reference-architecture",
            "severity": "error",
        },
    },
    {
        "type": "max-class-fanout",
        "group": "shape",
        "title": "A class may not reference too many classes",
        "summary": "Fails when a class references more than `limit` other classes.",
        "entry": {
            "id": "max-fanout",
            "type": "max-class-fanout",
            "severity": "warning",
            "limit": 10,
        },
    },
    {
        "type": "subclass-naming",
        "group": "shape",
        "title": "Subclasses of a base follow a name pattern",
        "summary": "Fails when a subclass of `base` has a name that does not match `name_pattern`.",
        "entry": {
            "id": "repositories-are-named-repository",
            "type": "subclass-naming",
            "severity": "error",
            "base": "*Repository",
            "name_pattern": ".*Repository",
        },
    },
    {
        "type": "dangling-classes",
        "group": "shape",
        "title": "No unused classes",
        "summary": "Fails for a class that no other class references. List the entry points of the program.",
        "entry": {
            "id": "no-unused-classes",
            "type": "dangling-classes",
            "severity": "warning",
            "entry_points": ["myapp.main.*"],
        },
    },
    {
        "type": "tag-conformance",
        "group": "source",
        "title": "The code obeys its own tags",
        "summary": "Reads the method bodies and checks the `@sealed`, `@immutable`, `@factory` and `@no_instantiation` tags.",
        "entry": {
            "id": "tags-must-be-honoured",
            "type": "tag-conformance",
            "severity": "error",
        },
    },
    {
        "type": "implementation-locks",
        "group": "source",
        "title": "A locked body may not change",
        "summary": "Fails when the body of a `@locked` class or function changes. Accept a change with `cdec check --automatic-exceptions locks --force`.",
        "entry": {
            "id": "frozen-implementations",
            "type": "implementation-locks",
            "severity": "error",
        },
    },
]


def starters() -> list[dict[str, Any]]:
    """The gallery, with the facts that come from the rule classes."""
    out = []
    for starter in _STARTERS:
        cls = get_rule_class(starter["type"])
        assert cls is not None, starter["type"]
        out.append(
            {
                **starter,
                "needs_reference": cls.default_scope == "diff"
                or starter["type"] == "reference-architecture",
            }
        )
    return out
