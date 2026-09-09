# Svelte 5 example

A tiny Svelte 5 storefront for the bookstore domain. Each `.svelte` file is
modelled as one UML class — the component itself — with attributes derived
from top-level `let`/`const` declarations (rune helpers like `$state`,
`$derived`, `$props` are surfaced in the attribute's default so they're
visible on the diagram) and operations from top-level functions. Component
references in markup become association edges via their import paths.

Layout:

```
src/
  lib/
    catalog.ts        Author, Book                 — plain TS classes
    cart.ts           Cart, CartLine               — plain TS class + interface
  components/
    PriceTag.svelte   leaf component, takes props
    BookCard.svelte   uses PriceTag, takes a Book
    CartView.svelte   uses PriceTag, takes a Cart
  routes/
    Storefront.svelte composes BookCard + CartView, holds the Cart state
```

Dependencies the diagram should highlight:

- `Storefront` → `BookCard`, `CartView` (markup component references)
- `Storefront` → `Cart`, `Book`, `Author` (typed attributes / `new` calls)
- `BookCard` → `PriceTag` (markup) and `Book` (typed prop)
- `CartView` → `PriceTag` (markup) and `Cart` (typed prop)
- `Cart` → `Book` (typed property on `CartLine`)

## Running

Web UI:

```bash
.venv/Scripts/python.exe -m code_constraints.cli serve
# → http://127.0.0.1:8765
```

Then **Change project** → paste `<repo>/examples/svelte_demo` with
language **svelte**.

CLI:

```bash
.venv/Scripts/python.exe -m code_constraints.cli parse examples/svelte_demo \
  --lang svelte --out svelte_demo.xmi
```

## How attributes get labelled

The Svelte parser surfaces rune helpers in the attribute's default field so
the diagram makes reactivity obvious:

- `let count = $state(0);`    → attribute `count`, default `$state(0)`
- `let total = $derived(...)` → attribute `total`, default `$derived(...)`
- `let { foo, bar = 0 } = $props();` → attributes `foo`, `bar`, type `$props`

A markup reference like `<BookCard {book} onAdd={handleAdd} />` becomes a
private attribute on the enclosing component class whose type is the
imported component's qualified name, so `resolve_association` draws an
edge to the target component.

## Limitations

- The parser is syntactic-only; identifiers that flow through aliased
  imports may show as the alias rather than the source's qualified name.
- Reactive *statements* (`$effect(...)` blocks) at the top level are not
  yet extracted as operations — only `function` declarations are.
- This demo does not exercise activity / sequence diagrams (not yet
  supported for `.svelte` / `.ts` sources).
