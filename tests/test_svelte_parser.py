"""Parse the svelte_demo fixture and assert component dependencies."""

from __future__ import annotations

from pathlib import Path

from code_constraints.core.associations import resolve_association
from code_constraints.svelte import parse_project

FIXTURE = Path(__file__).parent / "fixtures" / "svelte_demo"


def _find_class(project, qualified_name):
    return next(c for c in project.iter_classes() if c.qualified_name == qualified_name)


def test_svelte_file_becomes_component_class() -> None:
    project = parse_project(FIXTURE)
    cart = _find_class(project, "src.components.CartView")
    assert cart.name == "CartView"
    assert cart.kind == "class"


def test_top_level_let_declarations_become_attributes() -> None:
    project = parse_project(FIXTURE)
    cart = _find_class(project, "src.components.CartView")
    names = {a.name for a in cart.attributes}
    # Reactive state, plain values and the typed `cart` should all show up.
    assert "count" in names
    assert "cart" in names
    assert "total" in names


def test_rune_helpers_surface_in_attribute_default() -> None:
    project = parse_project(FIXTURE)
    cart = _find_class(project, "src.components.CartView")
    count = next(a for a in cart.attributes if a.name == "count")
    assert count.default is not None and count.default.startswith("$state")
    total = next(a for a in cart.attributes if a.name == "total")
    assert total.default is not None and total.default.startswith("$derived")


def test_props_destructuring_yields_named_attributes() -> None:
    project = parse_project(FIXTURE)
    badge = _find_class(project, "src.components.Badge")
    names = {a.name for a in badge.attributes}
    assert "label" in names
    assert "count" in names


def test_top_level_function_becomes_operation() -> None:
    project = parse_project(FIXTURE)
    cart = _find_class(project, "src.components.CartView")
    add = next(o for o in cart.operations if o.name == "addItem")
    assert add.return_type == "void"
    assert any(p.name == "item" for p in add.parameters)


def test_component_used_in_markup_becomes_association() -> None:
    """Importing `<Badge>` and using it in markup should create an attribute
    whose type resolves (via `resolve_association`) to the Badge component."""
    project = parse_project(FIXTURE)
    cart = _find_class(project, "src.components.CartView")
    # There should be a dependency attribute whose type points at the Badge
    # component's qualified name.
    badge_qn = "src.components.Badge"
    refs = [a for a in cart.attributes if a.type == badge_qn]
    assert refs, f"expected an attribute referencing {badge_qn}"
    target, _ = resolve_association(refs[0].type, project)
    assert target == badge_qn


def test_plain_ts_files_are_also_parsed() -> None:
    project = parse_project(FIXTURE)
    cart_class = _find_class(project, "src.lib.Cart")
    assert any(o.name == "add" for o in cart_class.operations)
    iface = _find_class(project, "src.lib.CartItem")
    assert iface.kind == "interface"


def test_typed_attribute_resolves_to_project_class() -> None:
    """The `cart: Cart` declaration inside the component script should still
    flow through `resolve_association` to the `src.lib.Cart` class."""
    project = parse_project(FIXTURE)
    cart_view = _find_class(project, "src.components.CartView")
    cart_attr = next(a for a in cart_view.attributes if a.name == "cart")
    target, _ = resolve_association(cart_attr.type, project)
    assert target == "src.lib.Cart"


def test_source_language_is_svelte() -> None:
    project = parse_project(FIXTURE)
    assert project.source_language == "svelte"
