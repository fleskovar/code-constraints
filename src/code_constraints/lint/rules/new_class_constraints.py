"""Rule: a new class must extend an approved base and obey the constraints of
its language.

Example: a new class is accepted only when it derives from `Notifier` and, in
C#, is `sealed`.
"""

from __future__ import annotations

from typing import Any, Iterable, Iterator

from code_constraints.core.model import Class, DiffStatus
from code_constraints.lint.rules import register
from code_constraints.lint.rules.base import (
    Rule,
    RuleContext,
    RuleSkipped,
    Violation,
    ancestors,
    match_any_glob,
    short_name,
)

# The constraints that exist in one language only. They sit under the language
# name in the rule entry and apply only when the project is in that language.
# Both read `Class.modifiers`, which only these two parsers fill.
LANGUAGE_OPTIONS: dict[str, tuple[str, ...]] = {
    "csharp": ("require_modifiers", "forbid_modifiers"),
    "python": ("require_metaclass", "forbid_metaclass"),
}


@register("new-class-constraints")
class NewClassConstraints(Rule):
    """A new class must extend an approved base and obey the constraints of its language.

    Options:
      bases:    globs. The class must derive from a match, directly or through
                project classes. A glob is matched against the base as written,
                its short name, and the qualified name of the project class it
                resolves to.
      csharp:   applies to a C# project only.
        require_modifiers:  globs. Each one must match a declared modifier
                            keyword (`sealed`, `static`, `internal`).
        forbid_modifiers:   globs. None may match a declared modifier keyword.
      python:   applies to a Python project only.
        require_metaclass:  globs. The class must declare a metaclass that
                            matches one of them.
        forbid_metaclass:   globs. The class must not declare a metaclass that
                            matches one of them.

    The metaclass is the declared `metaclass=` keyword: a metaclass that a
    class inherits from its base is not seen.

    Diff rule: checks the classes that are not in the baseline. With
    `scope: snapshot` it checks every class.
    """

    default_scope = "diff"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._validate_options()

    def check(self, ctx: RuleContext) -> Iterable[Violation]:
        language = ctx.project.source_language
        bases = _globs(self.options.get("bases"))
        block = self.options.get(language) or {}
        specific = {name: globs for name in block if (globs := _globs(block[name]))}
        if not (bases or specific):
            raise RuleSkipped(
                f"no constraint applies to {language}: the entry has no 'bases' "
                f"and no '{language}' block"
            )

        for cls in ctx.project.iter_classes():
            if cls.status == DiffStatus.REMOVED or self.is_ignored(cls.qualified_name):
                continue
            if self.scope == "diff" and cls.status != DiffStatus.ADDED:
                continue
            for signature, reason in _failures(cls, ctx, bases, specific):
                yield self.emit(
                    qualified_name=cls.qualified_name,
                    signature=signature,
                    message=self.message_for(
                        qualified_name=cls.qualified_name, name=cls.name, reason=reason
                    )
                    or f"Class '{cls.qualified_name}' {reason}.",
                    location=cls.location,
                )

    def _validate_options(self) -> None:
        """Reject an option this rule does not know, when the entry is loaded.

        This rule is strict about its keys. A language-specific option at the
        top level, or under the wrong language, would otherwise be ignored and
        the rule would look like one that passed."""
        for key, block in self.options.items():
            if key == "bases":
                continue
            allowed = LANGUAGE_OPTIONS.get(key)
            if allowed is None:
                owner = next((lang for lang, opts in LANGUAGE_OPTIONS.items() if key in opts), None)
                hint = (
                    f"put it in a '{owner}:' block"
                    if owner
                    else f"the options are 'bases' and the blocks {', '.join(LANGUAGE_OPTIONS)}"
                )
                raise ValueError(f"unknown option {key!r}; {hint}")
            if not isinstance(block, dict):
                # ValueError, not TypeError: it is what the config loader reports.
                raise ValueError(f"'{key}' must be a mapping")  # noqa: TRY004
            unknown = sorted(set(block) - set(allowed))
            if unknown:
                raise ValueError(
                    f"unknown option {unknown[0]!r} in '{key}'; "
                    f"it accepts {', '.join(allowed)}"
                )


def _globs(raw: Any) -> list[str]:
    if not raw:
        return []
    return [str(g) for g in (raw if isinstance(raw, list) else [raw])]


def _failures(
    cls: Class, ctx: RuleContext, bases: list[str], specific: dict[str, list[str]]
) -> Iterator[tuple[str, str]]:
    """Yield `(signature, reason)` for each constraint that `cls` breaks.

    `specific` holds the options of the project language only, so a constraint
    of another language is never evaluated. The signature names the constraint,
    not the offending text, so one exception accepts one deviation and its key
    survives an edit of the class."""
    if bases and not _extends_any(cls, ctx, bases):
        yield "bases", f"does not inherit from an approved base ({', '.join(bases)})"

    # --- C# ---
    for glob in specific.get("require_modifiers", ()):
        if not any(match_any_glob(m, [glob]) for m in cls.modifiers):
            yield f"require:{glob}", f"does not have the required modifier '{glob}'"
    for glob in specific.get("forbid_modifiers", ()):
        hit = next((m for m in cls.modifiers if match_any_glob(m, [glob])), None)
        if hit is not None:
            yield f"forbid:{glob}", f"has the forbidden modifier '{hit}'"

    # --- Python ---
    metaclass = next(
        (m.split("=", 1)[1] for m in cls.modifiers if m.startswith("metaclass=")), None
    )
    required = specific.get("require_metaclass")
    if required and not _names_match(metaclass, required):
        yield (
            "require_metaclass",
            f"does not declare an approved metaclass ({', '.join(required)})",
        )
    forbidden = specific.get("forbid_metaclass")
    if forbidden and _names_match(metaclass, forbidden):
        yield "forbid_metaclass", f"declares the forbidden metaclass '{metaclass}'"


def _names_match(type_text: str | None, globs: list[str]) -> bool:
    """True when the type as written, or its short name, matches a glob."""
    if type_text is None:
        return False
    return match_any_glob(type_text, globs) or match_any_glob(short_name(type_text), globs)


def _extends_any(cls: Class, ctx: RuleContext, globs: list[str]) -> bool:
    for base, parent in ancestors(cls, ctx):
        if _names_match(base, globs):
            return True
        if parent is not None and match_any_glob(parent.qualified_name, globs):
            return True
    return False
