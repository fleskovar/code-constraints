"""Resolve a typed attribute to a project class for association edges.

Extracted from `dot.py` so the SvelteFlow JSON model and DOT emitter can share
the same wrapper-stripping and lookup rules without circular imports.
"""

from __future__ import annotations

from code_constraints.core.model import Project

# Common .NET / Python collection wrappers whose inner type is the real
# association target. Order does not matter — these are matched by exact head.
COLLECTION_WRAPPERS = (
    "List", "IList", "IReadOnlyList", "ICollection", "IReadOnlyCollection",
    "IEnumerable", "HashSet", "ISet", "Queue", "Stack",
    "ObservableCollection", "ConcurrentBag", "ConcurrentQueue",
    "list", "set", "tuple", "frozenset", "Iterable", "Sequence", "Collection",
)

_DICTIONARY_HEADS = (
    "Dictionary", "IDictionary", "IReadOnlyDictionary", "dict", "Map", "Mapping",
)

# Single-arg unwrap heads (Python typing). `Optional[T]` collapses to T.
_OPTIONAL_HEADS = ("Optional",)


def build_class_index(project: Project) -> dict[str, str]:
    """Map both qualified and (when unambiguous) short class names → qualified name.

    Cached on the Project instance so repeated callers share the work.
    """
    cached: dict[str, str] | None = getattr(project, "_assoc_index", None)
    if cached is not None:
        return cached

    index: dict[str, str] = {}
    short_counts: dict[str, int] = {}
    for cls in project.iter_classes():
        index[cls.qualified_name] = cls.qualified_name
        short_counts[cls.name] = short_counts.get(cls.name, 0) + 1
    for cls in project.iter_classes():
        if short_counts[cls.name] == 1:
            index.setdefault(cls.name, cls.qualified_name)

    object.__setattr__(project, "_assoc_index", index)
    return index


def resolve_association(raw_type: str, project: Project) -> tuple[str | None, str]:
    """Return (target qualified name, multiplicity) for an attribute type, or
    (None, "") if it doesn't reference a project class.

    Multiplicity is "*" for arrays / collections / dictionaries and "" otherwise.
    """
    if not raw_type:
        return None, ""

    candidate = raw_type.strip()
    multiplicity = ""

    if candidate.endswith("?"):
        candidate = candidate[:-1].strip()

    while candidate.endswith("[]") or candidate.endswith("[,]"):
        candidate = candidate.rsplit("[", 1)[0].strip()
        multiplicity = "*"

    if "<" in candidate and candidate.endswith(">"):
        head, _, rest = candidate.partition("<")
        inner = rest[:-1]
        head = head.strip()
        if head in COLLECTION_WRAPPERS or head.split(".")[-1] in COLLECTION_WRAPPERS:
            multiplicity = "*"
            candidate = _split_generic_args(inner)[0].strip()
        elif head in _DICTIONARY_HEADS:
            multiplicity = "*"
            args = _split_generic_args(inner)
            candidate = args[-1].strip() if args else ""
        else:
            candidate = head

    # Python 3.9+ subscript generics: `list[T]`, `dict[K,V]`, `Optional[T]`.
    # Mirrors the `<>` block above but with `[]` brackets.
    elif "[" in candidate and candidate.endswith("]"):
        head, _, rest = candidate.partition("[")
        inner = rest[:-1]
        head = head.strip()
        if head in COLLECTION_WRAPPERS or head.split(".")[-1] in COLLECTION_WRAPPERS:
            multiplicity = "*"
            candidate = _split_generic_args(inner)[0].strip()
        elif head in _DICTIONARY_HEADS:
            multiplicity = "*"
            args = _split_generic_args(inner)
            candidate = args[-1].strip() if args else ""
        elif head in _OPTIONAL_HEADS:
            # Optional[T] is just T with allow-None semantics — keep
            # multiplicity unchanged ("" by default).
            args = _split_generic_args(inner)
            candidate = args[0].strip() if args else ""
        else:
            candidate = head

    candidate = candidate.split(".")[-1] if candidate else candidate
    if not candidate:
        return None, ""

    index = build_class_index(project)
    target = index.get(candidate) or index.get(raw_type)
    if target is None:
        return None, ""
    return target, multiplicity


def _split_generic_args(inner: str) -> list[str]:
    """Split a comma-separated generic-arg list, respecting nested <> and []."""
    out: list[str] = []
    depth = 0
    current: list[str] = []
    for ch in inner:
        if ch in ("<", "["):
            depth += 1
            current.append(ch)
        elif ch in (">", "]"):
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            out.append("".join(current))
            current = []
        else:
            current.append(ch)
    if current:
        out.append("".join(current))
    return out
