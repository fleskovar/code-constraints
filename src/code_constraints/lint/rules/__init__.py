"""Rule registry. Importing this package side-effect-registers every rule."""

from __future__ import annotations

from typing import Type

from code_constraints.lint.rules.base import Rule

_REGISTRY: dict[str, Type[Rule]] = {}


def register(type_name: str):
    def decorator(cls: Type[Rule]) -> Type[Rule]:
        cls.type_name = type_name
        _REGISTRY[type_name] = cls
        return cls

    return decorator


def get_rule_class(type_name: str) -> Type[Rule] | None:
    return _REGISTRY.get(type_name)


def known_rule_types() -> list[str]:
    return sorted(_REGISTRY.keys())


# Side-effect imports — every rule module must be imported here so its
# @register decorator runs.
from code_constraints.lint.rules import (  # noqa: E402, F401
    no_new_classes,
    no_removed_classes,
    dangling_classes,
    frozen_members,
    frozen_rules,
    forbidden_references,
    forbidden_package_references,
    layer_dependencies,
    subclass_naming,
    cyclic_package_dependencies,
    max_class_fanout,
)
