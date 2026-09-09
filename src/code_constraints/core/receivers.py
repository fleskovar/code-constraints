"""Receiver resolution for languages that declare operations outside their type.

Odin (`proc(inv: ^Invoice, …)`) and Julia (`f(inv::Invoice, …)`) both model an
operation's owner as the type of its first parameter. Three consumers need that
answer to agree exactly — the UML parser, the `cdec lock` fingerprinter, and the
`cdec enforce` analyzer — because a target name an agent reads from one has to be
the target the others accept. The lookup *policy* lives here so there is one
definition of it rather than three.
"""

from __future__ import annotations

from typing import TypeVar

T = TypeVar("T")


def resolve_owner(
    name: str, package_qn: str, index: dict[tuple[str, str], T]
) -> T | None:
    """Find the type `name` refers to from within `package_qn`.

    Same package first — the normal case, and the only one a compiler would
    resolve without imports. Falling back to a project-wide match by bare name
    is the best a syntactic parse can do; it is deliberately skipped when the
    name is ambiguous, so a wrong owner is never guessed.
    """
    if not name:
        return None
    same_package = index.get((package_qn, name))
    if same_package is not None:
        return same_package
    matches = [value for (_pkg, other), value in index.items() if other == name]
    return matches[0] if len(matches) == 1 else None
