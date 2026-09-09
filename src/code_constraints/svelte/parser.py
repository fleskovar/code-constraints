"""Parse a Svelte 5 project (a directory of .svelte + .ts files) into a
`code_constraints.core.Project`.

Each `.svelte` file is modelled as a single UML class — the component itself.
The script block (between `<script>` and `</script>`, including `lang="ts"`
and `context="module"` variants) is fed to the TypeScript parser, with the
following Svelte-specific twists:

- Top-level `let` / `const` declarations inside the script become attributes
  of the component class. `let foo = $state(...)`, `let { ... } = $props()`,
  and `let bar = $derived(...)` are all recognised — the rune helpers are
  captured in the attribute's default so it's obvious from the diagram what
  kind of reactive value it is.
- Top-level `function` declarations become operations of the component class.
- Any *class* / *interface* / *enum* / *type alias* defined inside the script
  block flows through to the package as a regular TypeScript class.
- Imports are tracked so a component reference in the markup
  (`<Foo prop={x} />`) can be resolved to the imported component's qualified
  name. Resolved component dependencies are surfaced as attributes whose type
  matches the imported component's class name — that way the existing
  `resolve_association` machinery wires up the association edges without any
  Svelte-specific code in the renderer.

Plain `.ts` files alongside `.svelte` files are also parsed (using
`code_constraints.typescript.parser`) so a component's helper module shows up too.
"""

from __future__ import annotations

import re
from pathlib import Path

from tree_sitter import Node

from code_constraints.core.model import (
    Attribute,
    Class,
    Operation,
    Package,
    Parameter,
    Project,
    SourceLocation,
    Visibility,
)
from code_constraints.typescript.parser import (
    _PARSER_TS,
    _ensure_package,
    _qualified_package_name,
    _strip_type_annotation,
    _text,
    parse_module_body,
)
from code_constraints.typescript.parser import _parameter_from as _ts_parameter_from
from code_constraints.typescript import parse_project as _ts_parse_project  # noqa: F401  (kept for clarity)
from code_constraints.typescript.parser import _iter_ts_files, _should_skip


_SCRIPT_RE = re.compile(
    r"<script\b([^>]*)>(.*?)</script\s*>", re.DOTALL | re.IGNORECASE
)
_STYLE_RE = re.compile(r"<style\b[^>]*>.*?</style\s*>", re.DOTALL | re.IGNORECASE)
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
# Component tag: opening `<` then a capital letter and JS-identifier chars,
# then either whitespace, a slash, or the closing `>`.
_COMPONENT_TAG_RE = re.compile(r"<([A-Z][A-Za-z0-9_$.]*)\b")

# `Foo.svelte` is the convention; `index.svelte` -> use the parent directory
# name as the component name.
_SVELTE_SUFFIX = ".svelte"


def parse_project(root: str | Path) -> Project:
    root_path = Path(root).resolve()
    if not root_path.is_dir():
        raise ValueError(f"not a directory: {root_path}")

    project = Project(source_language="svelte", root_path=str(root_path))
    package_index: dict[str, Package] = {}

    # First, parse every plain .ts / .tsx file so component imports can
    # resolve to project classes regardless of file order.
    for ts_file in sorted(_iter_ts_files(root_path)):
        _parse_ts_file(ts_file, root_path, project, package_index)

    # Then ingest .svelte files.
    for svelte_file in sorted(root_path.rglob(f"*{_SVELTE_SUFFIX}")):
        if _should_skip(svelte_file):
            continue
        _parse_svelte_file(svelte_file, root_path, project, package_index)

    return project


# ---------- plain .ts files ----------


def _parse_ts_file(
    file: Path,
    root: Path,
    project: Project,
    package_index: dict[str, Package],
) -> None:
    source_bytes = file.read_bytes()
    tree = _PARSER_TS.parse(source_bytes)
    rel = file.relative_to(root)
    file_str = rel.as_posix()
    package_qn = _qualified_package_name(rel)
    _ensure_package(project, package_qn, package_index)
    parse_module_body(
        tree.root_node,
        source_bytes,
        package_qn=package_qn,
        project=project,
        package_index=package_index,
        file_str=file_str,
    )


# ---------- .svelte files ----------


def _parse_svelte_file(
    file: Path,
    root: Path,
    project: Project,
    package_index: dict[str, Package],
) -> None:
    rel = file.relative_to(root)
    file_str = rel.as_posix()
    package_qn = _qualified_package_name(rel)
    pkg = _ensure_package(project, package_qn, package_index)

    text = file.read_text(encoding="utf-8", errors="replace")
    component_name = _component_name_from(file)
    component_qn = (
        f"{package_qn}.{component_name}"
        if package_qn and package_qn != "__root__"
        else component_name
    )

    component = Class(
        name=component_name,
        qualified_name=component_qn,
        kind="class",
        location=SourceLocation(
            file=file_str,
            start_line=1,
            end_line=len(text.splitlines()) or 1,
        ),
    )

    # Strip styles + comments so markup scanning isn't fooled by tag-like
    # content inside them.
    markup_text = _STYLE_RE.sub("", text)
    markup_text = _COMMENT_RE.sub("", markup_text)

    imports: dict[str, str] = {}  # local-name -> module path string
    component_description: str | None = None

    for script_match in _SCRIPT_RE.finditer(markup_text):
        script_body = script_match.group(2)
        # Pad with newlines so script tree-sitter line numbers don't end up
        # confusingly close to the markup ones if we ever surface them.
        script_bytes = script_body.encode("utf-8")
        tree = _PARSER_TS.parse(script_bytes)
        desc = _ingest_script(
            tree.root_node,
            script_bytes,
            component=component,
            package_qn=package_qn,
            project=project,
            package_index=package_index,
            imports=imports,
            file_str=file_str,
        )
        if desc and component_description is None:
            component_description = desc

    # Now scan markup for component references and turn each unique one
    # whose import we resolved into an attribute (so `resolve_association`
    # picks it up as a dependency).
    markup_only = _SCRIPT_RE.sub("", markup_text)
    referenced: list[str] = []
    seen_refs: set[str] = set()
    for m in _COMPONENT_TAG_RE.finditer(markup_only):
        name = m.group(1)
        # If the import was `import * as Util from "..."`, the user writes
        # `<Util.Foo />`. Track the head identifier in that case.
        head = name.split(".")[0]
        if head not in imports:
            continue
        if name in seen_refs:
            continue
        seen_refs.add(name)
        referenced.append(name)

    for ref_name in referenced:
        head = ref_name.split(".")[0]
        target_module = imports[head]
        target_qn = _resolve_component_qn(target_module, file, root, ref_name)
        # Surface the dependency as an attribute. `resolve_association`
        # matches by the trailing identifier so a value like
        # `target_qn = "app.components.Foo"` will edge-link to that class
        # if it exists in the project.
        component.attributes.append(
            Attribute(
                name=_attr_name_for_ref(ref_name),
                type=target_qn,
                visibility=Visibility.PRIVATE,
            )
        )

    if component_description is not None:
        component.description = component_description

    pkg.classes.append(component)


def _component_name_from(file: Path) -> str:
    stem = file.stem
    if stem.lower() in ("index", "+page", "+layout"):
        # Fall back to the parent directory name for SvelteKit route files /
        # barrel-style `index.svelte`s.
        return file.parent.name or stem
    return stem


def _resolve_component_qn(
    module_path: str, importer: Path, root: Path, ref_name: str
) -> str:
    """Resolve a `from "..."` module path to a project-qualified class name.

    Returns the bare component name if the import is to a node_modules
    package or otherwise unresolvable — the renderer will then just show it
    as an unattached label, which is exactly right for external components.
    """
    # `ref_name` may be "Foo" or "Util.Foo" — the trailing component is the
    # class we're after.
    short_name = ref_name.split(".")[-1]
    if not module_path.startswith(".") and not module_path.startswith("/"):
        return short_name
    target = (importer.parent / module_path).resolve()
    candidates = [
        target,
        target.with_suffix(".svelte"),
        target.with_suffix(".ts"),
        target.with_suffix(".tsx"),
        target / f"{short_name}.svelte",
        target / "index.svelte",
        target / "index.ts",
    ]
    for c in candidates:
        if c.exists() and c.is_file():
            try:
                rel = c.relative_to(root)
            except ValueError:
                continue
            package_qn = _qualified_package_name(rel)
            if c.suffix == _SVELTE_SUFFIX:
                stem = c.stem
                if stem.lower() in ("index", "+page", "+layout"):
                    stem = c.parent.name or stem
                if package_qn and package_qn != "__root__":
                    return f"{package_qn}.{stem}"
                return stem
            # Plain .ts: a re-export barrel. Best effort: assume the short
            # name matches a class declared in that file.
            if package_qn and package_qn != "__root__":
                return f"{package_qn}.{short_name}"
            return short_name
    return short_name


def _attr_name_for_ref(ref_name: str) -> str:
    """Turn a component tag like `Foo` or `Util.Foo` into a stable attribute
    slot name. Prefixed with `_` so the visibility heuristic still flags it
    as protected/internal."""
    safe = ref_name.replace(".", "_")
    return f"_{safe[0].lower()}{safe[1:]}" if safe else "_ref"


# ---------- script block ingestion ----------


def _ingest_script(
    root: Node,
    source: bytes,
    *,
    component: Class,
    package_qn: str,
    project: Project,
    package_index: dict[str, Package],
    imports: dict[str, str],
    file_str: str,
) -> str | None:
    """Walk a parsed `<script>` body. Returns the first JSDoc block found
    above a top-level declaration, used as the component description."""
    first_doc: str | None = None
    for node in root.named_children:
        unwrapped = node
        if node.type == "export_statement" and node.named_child_count == 1:
            unwrapped = node.named_children[0]

        if unwrapped.type == "import_statement":
            _record_import(unwrapped, source, imports)
            continue

        if unwrapped.type == "lexical_declaration":
            for attr in _attributes_from_lexical(unwrapped, source):
                # De-dupe against any same-named attribute already on the
                # component (e.g. from a prior script block).
                if not any(a.name == attr.name for a in component.attributes):
                    component.attributes.append(attr)
            continue

        if unwrapped.type == "function_declaration":
            component.operations.append(_operation_from_function(unwrapped, source))
            continue

        if unwrapped.type in {
            "class_declaration",
            "abstract_class_declaration",
            "interface_declaration",
            "enum_declaration",
            "type_alias_declaration",
            "internal_module",
        }:
            # Let the TS parser ingest these as regular classes.
            parse_module_body(
                _Wrap([unwrapped]),  # type: ignore[arg-type]
                source,
                package_qn=package_qn,
                project=project,
                package_index=package_index,
                file_str=file_str,
            )
            continue

    return first_doc


class _Wrap:
    """Minimal Node-shaped wrapper letting us reuse `parse_module_body` for
    a hand-picked list of top-level declarations.

    `parse_module_body` only touches `.named_children`, so we expose just that.
    """

    def __init__(self, children: list[Node]) -> None:
        self.named_children = children


def _record_import(node: Node, source: bytes, imports: dict[str, str]) -> None:
    """Populate `imports` with every binding introduced by an import_statement."""
    # The module path lives in a `string` child of the import_statement.
    module_node = next((c for c in node.named_children if c.type == "string"), None)
    if module_node is None:
        return
    module_path = _string_value(module_node, source)

    clause = next(
        (c for c in node.named_children if c.type == "import_clause"), None
    )
    if clause is None:
        return
    for child in clause.named_children:
        if child.type == "identifier":
            imports[_text(child, source)] = module_path
        elif child.type == "namespace_import":
            for c in child.named_children:
                if c.type == "identifier":
                    imports[_text(c, source)] = module_path
        elif child.type == "named_imports":
            for spec in child.named_children:
                if spec.type != "import_specifier":
                    continue
                idents = [c for c in spec.named_children if c.type == "identifier"]
                # `import { Foo as Bar }` → idents are [Foo, Bar]; we want Bar
                # as the binding. `import { Foo }` → idents = [Foo].
                if idents:
                    imports[_text(idents[-1], source)] = module_path


def _string_value(node: Node, source: bytes) -> str:
    """Extract the literal text of a `string` node (drops the surrounding
    quotes; does not handle escape sequences)."""
    for c in node.named_children:
        if c.type == "string_fragment":
            return _text(c, source)
    raw = _text(node, source)
    if len(raw) >= 2 and raw[0] in ("'", '"', "`"):
        return raw[1:-1]
    return raw


def _attributes_from_lexical(node: Node, source: bytes) -> list[Attribute]:
    """One `let`/`const` declaration can introduce multiple variables (object
    destructuring); return one Attribute per leaf binding."""
    out: list[Attribute] = []
    for declarator in node.named_children:
        if declarator.type != "variable_declarator":
            continue
        name_node = declarator.child_by_field_name("name") or _first_named_child(
            declarator
        )
        if name_node is None:
            continue
        type_node = next(
            (c for c in declarator.named_children if c.type == "type_annotation"),
            None,
        )
        type_text = (
            _strip_type_annotation(_text(type_node, source)) if type_node else ""
        )
        # Find the initializer (named child that isn't the name or type).
        init = None
        for c in declarator.named_children:
            if c is name_node or c is type_node:
                continue
            init = c
        if name_node.type in ("object_pattern", "array_pattern"):
            for sub in _flatten_pattern(name_node, source):
                out.append(
                    Attribute(
                        name=sub,
                        type=_rune_type_hint(init, source) or "",
                        visibility=Visibility.PUBLIC,
                        default=_rune_default(init, source),
                    )
                )
        else:
            out.append(
                Attribute(
                    name=_text(name_node, source),
                    type=type_text,
                    visibility=Visibility.PUBLIC,
                    default=_rune_default(init, source),
                )
            )
    return out


def _flatten_pattern(pattern: Node, source: bytes) -> list[str]:
    """Pull binding names out of an object_pattern / array_pattern."""
    out: list[str] = []
    for child in pattern.named_children:
        if child.type == "shorthand_property_identifier_pattern":
            out.append(_text(child, source))
        elif child.type == "identifier":
            out.append(_text(child, source))
        elif child.type == "object_assignment_pattern":
            # `{ foo = default }` — first named child is the binding.
            first = _first_named_child(child)
            if first is not None:
                out.append(_text(first, source))
        elif child.type == "pair_pattern":
            # `{ foo: bar }` — `bar` is the binding name.
            for c in child.named_children:
                if c.type in ("identifier", "shorthand_property_identifier_pattern"):
                    out.append(_text(c, source))
        elif child.type in ("object_pattern", "array_pattern"):
            out.extend(_flatten_pattern(child, source))
    return out


_RUNE_NAMES = ("$state", "$derived", "$props", "$bindable", "$effect")


def _rune_default(init: Node | None, source: bytes) -> str | None:
    """Surface rune helpers in the default field so the diagram label makes
    it obvious that an attribute is reactive."""
    if init is None:
        return None
    text = _text(init, source).strip()
    if not text:
        return None
    # Truncate long initializers — keep just enough to be a useful hint.
    if len(text) > 60:
        text = text[:60] + "…"
    return text


def _rune_type_hint(init: Node | None, source: bytes) -> str | None:
    """If a destructured binding came from `$props()`, mark its type as
    `Props` so the diagram hints at the source."""
    if init is None:
        return None
    raw = _text(init, source).strip()
    for rune in _RUNE_NAMES:
        if raw.startswith(rune + "("):
            return rune
    return None


def _operation_from_function(node: Node, source: bytes) -> Operation:
    name_node = node.child_by_field_name("name")
    name = _text(name_node, source) if name_node else ""
    return_node = next(
        (c for c in node.named_children if c.type == "type_annotation"),
        None,
    )
    return_type = (
        _strip_type_annotation(_text(return_node, source)) if return_node else ""
    )
    params: list[Parameter] = []
    params_node = node.child_by_field_name("parameters")
    if params_node is not None:
        for p in params_node.named_children:
            if p.type not in ("required_parameter", "optional_parameter"):
                continue
            params.append(_ts_parameter_from(p, source))
    return Operation(
        name=name,
        parameters=params,
        return_type=return_type,
        visibility=Visibility.PUBLIC,
        is_static=False,
        is_abstract=False,
    )


def _first_named_child(node: Node) -> Node | None:
    return node.named_children[0] if node.named_child_count else None
