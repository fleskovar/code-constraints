"""Canonical catalog of architectural-rule tags.

Single source of truth shared by the parsers (recognition), the web app
(presentation), and both enforcement engines (`cdec check` drift rules and the
`cdec enforce` conformance command). Add a rule here once; every other module
looks it up by id / python name / csharp name rather than hard-coding strings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Target = Literal["class", "operation"]
Enforcement = Literal["drift", "architectural", "implementation", "lock"]


@dataclass(frozen=True)
class RuleSpec:
    id: str  # canonical kebab-case id, e.g. "no-instantiation"
    python_name: str  # decorator name as imported from the shim, e.g. "no_instantiation"
    csharp_name: str  # attribute name without the "Attribute" suffix, e.g. "NoInstantiation"
    targets: frozenset[Target]
    params: tuple[str, ...] = ()  # recognised keyword parameter names
    enforcement: Enforcement = "drift"
    summary: str = ""
    # Julia macro name without the leading `@`, e.g. "no_instantiation".
    julia_name: str = ""
    # Name used in the `---@cdec <name>(...)` / `//@cdec <name>(...)` annotation
    # comments that carry tags in Lua and Odin (neither language has a
    # user-extensible decorator/attribute syntax — see the annotation note below).
    annotation_name: str = ""

    def __post_init__(self) -> None:
        # The Julia macro and the Lua/Odin annotation keyword both default to the
        # Python decorator name; every language then spells one vocabulary.
        if not self.julia_name:
            object.__setattr__(self, "julia_name", self.python_name)
        if not self.annotation_name:
            object.__setattr__(self, "annotation_name", self.python_name)


_SPECS: tuple[RuleSpec, ...] = (
    RuleSpec(
        id="no-instantiation",
        python_name="no_instantiation",
        csharp_name="NoInstantiation",
        targets=frozenset({"class", "operation"}),
        params=("allow",),
        enforcement="implementation",
        summary="May not construct objects (except types listed in `allow`).",
    ),
    RuleSpec(
        id="no-side-effects",
        python_name="no_side_effects",
        csharp_name="NoSideEffects",
        targets=frozenset({"operation"}),
        params=("allow",),
        enforcement="drift",
        summary="Must be free of side effects (body analysis deferred; tag is captured + frozen).",
    ),
    RuleSpec(
        id="sealed",
        python_name="sealed",
        csharp_name="Sealed",
        targets=frozenset({"class"}),
        enforcement="implementation",
        summary="May not be subclassed (composition over inheritance).",
    ),
    RuleSpec(
        id="immutable",
        python_name="immutable",
        csharp_name="Immutable",
        targets=frozenset({"class"}),
        enforcement="implementation",
        summary="Fields may not be reassigned after construction.",
    ),
    RuleSpec(
        id="factory",
        python_name="factory",
        csharp_name="Factory",
        targets=frozenset({"class", "operation"}),
        params=("creates",),
        enforcement="implementation",
        summary="Designated constructor of the types in `creates`; instantiation elsewhere is forbidden.",
    ),
    RuleSpec(
        id="locked",
        python_name="locked",
        csharp_name="Locked",
        targets=frozenset({"class", "operation"}),
        params=("reason", "owner"),
        enforcement="lock",
        summary=(
            "Implementation is frozen: any semantic change to the body fails "
            "`cdec lock check` until a lead re-baselines it."
        ),
    ),
    RuleSpec(
        id="layer",
        python_name="layer",
        csharp_name="Layer",
        targets=frozenset({"class"}),
        params=("name",),
        enforcement="architectural",
        summary="Assigns the class to an architectural layer for dependency-direction checks.",
    ),
)

RULE_CATALOG: dict[str, RuleSpec] = {spec.id: spec for spec in _SPECS}
_BY_PYTHON: dict[str, RuleSpec] = {spec.python_name: spec for spec in _SPECS}
_BY_CSHARP: dict[str, RuleSpec] = {spec.csharp_name: spec for spec in _SPECS}
_BY_JULIA: dict[str, RuleSpec] = {spec.julia_name: spec for spec in _SPECS}
_BY_ANNOTATION: dict[str, RuleSpec] = {spec.annotation_name: spec for spec in _SPECS}


def by_id(rule_id: str) -> RuleSpec | None:
    return RULE_CATALOG.get(rule_id)


def by_python_name(name: str) -> RuleSpec | None:
    return _BY_PYTHON.get(name)


def by_csharp_name(name: str) -> RuleSpec | None:
    """Look up by attribute name, tolerating the optional `Attribute` suffix."""
    spec = _BY_CSHARP.get(name)
    if spec is None and name.endswith("Attribute"):
        spec = _BY_CSHARP.get(name[: -len("Attribute")])
    return spec


def by_julia_name(name: str) -> RuleSpec | None:
    """Look up by Julia macro name, with or without the leading `@`."""
    return _BY_JULIA.get(name.lstrip("@"))


def by_annotation_name(name: str) -> RuleSpec | None:
    """Look up by the keyword used in a `@cdec` annotation comment (Lua, Odin)."""
    return _BY_ANNOTATION.get(name)


# Module names the Python shim is published under; the parser only treats a
# decorator as a rule when its base name was imported from one of these.
PYTHON_SHIM_MODULES: frozenset[str] = frozenset({"cdec_rules", "code_constraints.rules"})
# `using` namespace that gates C# attribute recognition.
CSHARP_SHIM_NAMESPACE = "CodeConstraints.Rules"
# Julia module the macro shim is published as; a `@macro` counts as a rule only
# when the file brings this module into scope (`using`/`import CdecRules`).
JULIA_SHIM_MODULES: frozenset[str] = frozenset({"CdecRules"})

# Lua and Odin have no user-extensible decorator or attribute syntax — Lua has
# no declaration modifiers at all, and the Odin compiler rejects any `@(...)`
# attribute it doesn't know, so a no-op `@(cdec_sealed)` would fail to build.
# Both therefore carry tags in a namespaced *annotation comment* placed directly
# above the declaration, in the slot a decorator would occupy:
#
#     ---@cdec sealed                 -- Lua  (LuaCATS-style `---@` comment)
#     ---@cdec layer("domain")
#     local Invoice = {}
#
#     //@cdec sealed                  // Odin
#     //@cdec layer("domain")
#     Invoice :: struct { ... }
#
# The `@cdec` prefix is the namespace, so it plays the gating role that the shim
# import plays in Python/C#/Julia: an unrelated annotation can never false-match.
ANNOTATION_MARKER = "@cdec"

# Shim files copied into a target project by `cdec init`. They declare the tag
# vocabulary as no-op functions, which would otherwise parse as a module of
# operations and show up as a class in the user's own diagrams. Parsers skip
# them by name. (Python and C# need no entry: their shims declare only
# functions / attribute classes that never reach the model.)
SHIM_FILENAMES: frozenset[str] = frozenset(
    {"cdec_rules.lua", "cdec_rules.odin", "CdecRules.jl"}
)
