"""AST fingerprinting for Python (`cdec lock`, Engine C).

Produces a digest per lockable element (module-level function, class, method,
nested class) that captures *semantic* content only:

  * line/column attributes are never serialised, so inserting code above a
    locked function leaves its digest untouched — the whole point of hashing the
    tree rather than a slice of the file;
  * comments aren't in the Python AST at all, and docstrings are stripped
    unless `include_docstrings=True`;
  * the `@locked` tag itself is stripped recursively, so adding or removing a
    lock (or a nested one) never invalidates an enclosing digest.

The canonical serialisation is hand-rolled rather than `ast.dump` so it stays
stable across CPython releases: fields that are `None` or empty are omitted, so
a newly-introduced optional AST field (e.g. `type_params` in 3.12) doesn't
silently change every digest. Any genuinely breaking change to this function
must bump `DIGEST_ALGO`, which surfaces as an `algo-mismatch` violation telling
the user to re-baseline rather than as a false "implementation changed".
"""

from __future__ import annotations

import ast
import copy
from hashlib import sha256
from pathlib import Path

from code_constraints.lock.model import LOCK_RULE, LockTarget
from code_constraints.python.rules_extract import ImportMap, build_import_map, extract_rules

DIGEST_ALGO = "py-ast/1"

_SKIP_DIR_NAMES = {"__pycache__", ".venv", "venv", ".tox", "build", "dist", ".git"}
# `type_comment` carries a `# type:` comment; it is documentation, not code.
_SKIP_FIELDS = {"type_comment"}

_FUNC_TYPES = (ast.FunctionDef, ast.AsyncFunctionDef)


def collect_lockables(
    root: str | Path, *, include_docstrings: bool = False
) -> list[LockTarget]:
    """Walk `root` and return every lockable element with its digest.

    Every element is returned, not just tagged ones: the engine needs digests
    for untagged elements too, so it can tell "someone deleted the @locked tag"
    apart from "the element is gone", and so `lock.targets:` globs can freeze
    code that isn't practical to decorate (e.g. a whole test package).
    """
    root_path = Path(root).resolve()
    out: list[LockTarget] = []
    for py_file in sorted(root_path.rglob("*.py")):
        if any(part in _SKIP_DIR_NAMES for part in py_file.parts):
            continue
        try:
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (OSError, SyntaxError, ValueError):
            continue
        rel = py_file.relative_to(root_path)
        import_map = build_import_map(tree)
        class_prefix, func_prefix = _scope_prefixes(rel)
        _collect_scope(
            tree.body,
            class_prefix=class_prefix,
            func_prefix=func_prefix,
            in_class=False,
            file=rel.as_posix(),
            import_map=import_map,
            include_docstrings=include_docstrings,
            out=out,
        )
    return out


def _scope_prefixes(rel: Path) -> tuple[str, str]:
    """Return (class_prefix, function_prefix) for a module.

    Classes use the *package* qualified name so lock targets line up with the
    qualified names everywhere else in the harness (`orders.Receipt`). Module
    functions additionally carry the module stem (`orders.billing.compute_tax`),
    since two modules in one package may define same-named functions.
    """
    pkg = ".".join(rel.parts[:-1])
    stem = rel.stem
    if stem == "__init__":
        module = pkg
    else:
        module = f"{pkg}.{stem}" if pkg else stem
    return pkg, module


def _collect_scope(
    body: list[ast.stmt],
    *,
    class_prefix: str,
    func_prefix: str,
    in_class: bool,
    file: str,
    import_map: ImportMap,
    include_docstrings: bool,
    out: list[LockTarget],
) -> None:
    """Group same-named siblings, digest each group, then recurse into classes.

    Grouping is what makes overloads (`@overload`, `@property` + `@x.setter`)
    behave: one target covers every sibling of that name, so adding, removing,
    or editing any of them moves the group digest.
    """
    groups: dict[str, list[ast.stmt]] = {}
    for node in body:
        if isinstance(node, (ast.ClassDef, *_FUNC_TYPES)):
            groups.setdefault(node.name, []).append(node)

    for name, nodes in groups.items():
        is_class = isinstance(nodes[0], ast.ClassDef)
        if is_class:
            target = f"{class_prefix}.{name}" if class_prefix else name
            kind = "class"
        else:
            prefix = class_prefix if in_class else func_prefix
            target = f"{prefix}.{name}" if prefix else name
            kind = "method" if in_class else "function"

        digests = sorted(
            _digest_node(n, import_map, include_docstrings) for n in nodes
        )
        digest = (
            digests[0]
            if len(digests) == 1
            else sha256(("group:" + "|".join(digests)).encode("utf-8")).hexdigest()
        )

        declared = False
        params: dict[str, str] = {}
        for n in nodes:
            for rule in extract_rules(n.decorator_list, import_map):
                if rule.name == LOCK_RULE:
                    declared = True
                    params = {**rule.kwargs, **params} if params else dict(rule.kwargs)

        out.append(
            LockTarget(
                target=target,
                kind=kind,  # type: ignore[arg-type]
                digest=digest,
                algo=DIGEST_ALGO,
                file=file,
                line=getattr(nodes[0], "lineno", 0),
                declared=declared,
                params=params,
            )
        )

        if is_class:
            for n in nodes:
                assert isinstance(n, ast.ClassDef)
                _collect_scope(
                    n.body,
                    class_prefix=target,
                    func_prefix=target,
                    in_class=True,
                    file=file,
                    import_map=import_map,
                    include_docstrings=include_docstrings,
                    out=out,
                )


# ---------- digest ----------

def _digest_node(
    node: ast.stmt, import_map: ImportMap, include_docstrings: bool
) -> str:
    clone = copy.deepcopy(node)
    _normalize(clone, import_map, include_docstrings)
    return sha256(_canonical(clone).encode("utf-8")).hexdigest()


def _normalize(node: ast.AST, import_map: ImportMap, include_docstrings: bool) -> None:
    """Strip lock tags and (optionally) docstrings from the whole subtree."""
    for sub in ast.walk(node):
        decorators = getattr(sub, "decorator_list", None)
        if decorators is not None:
            sub.decorator_list = [  # type: ignore[attr-defined]
                d for d in decorators if not _is_lock_decorator(d, import_map)
            ]
        if not include_docstrings and isinstance(
            sub, (ast.Module, ast.ClassDef, *_FUNC_TYPES)
        ):
            _strip_docstring(sub)


def _is_lock_decorator(dec: ast.expr, import_map: ImportMap) -> bool:
    return any(r.name == LOCK_RULE for r in extract_rules([dec], import_map))


def _strip_docstring(node: ast.AST) -> None:
    body = getattr(node, "body", None)
    if not body or not isinstance(body, list):
        return
    first = body[0]
    if (
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Constant)
        and isinstance(first.value.value, str)
    ):
        # A body must not become empty — `def f(): """doc"""` is legal Python.
        node.body = body[1:] if len(body) > 1 else [ast.Pass()]  # type: ignore[attr-defined]


def _canonical(node: object) -> str:
    """Serialise an AST to a deterministic string.

    Position attributes are excluded (they live in `_attributes`, not
    `_fields`). Empty and `None` fields are omitted so that AST fields added by
    future Python versions don't shift existing digests.
    """
    if isinstance(node, ast.AST):
        parts: list[str] = []
        for name, value in ast.iter_fields(node):
            if name in _SKIP_FIELDS or value is None:
                continue
            if isinstance(value, list) and not value:
                continue
            parts.append(f"{name}={_canonical(value)}")
        return f"{type(node).__name__}({','.join(parts)})"
    if isinstance(node, list):
        return "[" + ",".join(_canonical(v) for v in node) + "]"
    return repr(node)
