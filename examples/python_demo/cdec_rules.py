"""No-op architectural-rule decorators for code-constraints.

Import these to tag classes and methods with architectural constraints. They do
nothing at runtime — they exist so tagged code still imports/runs, and so the
UML parser can recognise the tags (it only treats a decorator as a rule when its
base name was imported from this module). Enforcement happens out-of-band via
`cdec check` (drift) and `cdec enforce` (implementation conformance).

    from cdec_rules import no_instantiation, factory, sealed, immutable, layer, locked

    @sealed
    @layer("domain")
    class Order: ...

    class OrderService:
        @no_instantiation(allow=["list", "dict"])
        def total(self): ...

        @locked(reason="agreed settlement sequence")
        def settle(self): ...
"""

from __future__ import annotations

from typing import Any, Callable, TypeVar

_T = TypeVar("_T")


def _passthrough(obj: _T) -> _T:
    return obj


def _decorator_factory(*_args: Any, **_kwargs: Any) -> Callable[[_T], _T]:
    return _passthrough


def no_instantiation(*args: Any, **kwargs: Any):
    """Forbid constructing objects in the tagged class/method body.

    `allow` (list[str]): type names that may still be instantiated (e.g.
    collections like "list", "dict")."""
    # Support both bare `@no_instantiation` and `@no_instantiation(allow=[...])`.
    if len(args) == 1 and not kwargs and callable(args[0]):
        return args[0]
    return _passthrough


def no_side_effects(*args: Any, **kwargs: Any):
    """Declare the tagged operation free of side effects."""
    if len(args) == 1 and not kwargs and callable(args[0]):
        return args[0]
    return _passthrough


def factory(*args: Any, **kwargs: Any):
    """Mark the tagged class/method as the designated factory for the types in
    `creates` (list[str]); constructing those types elsewhere is forbidden."""
    if len(args) == 1 and not kwargs and callable(args[0]):
        return args[0]
    return _passthrough


def layer(*args: Any, **kwargs: Any):
    """Assign the class to an architectural layer, e.g. `@layer("domain")`."""
    if len(args) == 1 and not kwargs and callable(args[0]):
        return args[0]
    return _passthrough


def locked(*args: Any, **kwargs: Any):
    """Freeze the tagged class/function implementation.

    The element's normalised AST is digested and recorded in `.cdec/locks.yaml`
    by `cdec lock set`. Any later semantic change to the body — or removal of
    this tag — fails `cdec lock check` (and `cdec check`, which runs it). Moving
    the element around the file, reformatting it, or editing comments does not
    trip the lock: the digest is computed from the AST, not the source text.

    Optional metadata: `reason` (why it's frozen) and `owner` (who to ask).
    Both are recorded in the lockfile and echoed in violation messages."""
    if len(args) == 1 and not kwargs and callable(args[0]):
        return args[0]
    return _passthrough


def sealed(obj: _T) -> _T:
    """Forbid subclassing the tagged class."""
    return obj


def immutable(obj: _T) -> _T:
    """Forbid reassigning the tagged class's fields after construction."""
    return obj
