# Per-language guides

The **[Tutorial](../TUTORIAL.md)** teaches the workflow; these guides teach *your language's
dialect of it*. Each one is a complete, runnable walk-through against that language's
bundled demo, covering every capability the language has — how classes are recovered from
code that may not have classes, how the tags are spelled, what each engine can and cannot
see, and the parser gotchas worth knowing before you trust a diagram.

Read the Tutorial first if you're new. Come here when you're pointing `cdec` at real code.

| Guide | Read it for |
|---|---|
| **[Python](PYTHON.md)** | `ast`-based parsing, decorator tags, heuristic construction detection |
| **[C#](CSHARP.md)** | tree-sitter parsing, attribute tags, precise construction detection |
| **[Odin](ODIN.md)** | Procedures-as-methods, `using` embedding, `//@cdec` comment tags |
| **[Lua](LUA.md)** | Table-and-metatable classes, `---@cdec` comment tags |
| **[Julia](JULIA.md)** | Multiple dispatch as methods, macro tags, space-separated arguments |
| **[TypeScript & Svelte](TYPESCRIPT-SVELTE.md)** | Modelling and the model rules on a parse-only language |

---

## Capability matrix

Support is **layered**, and the layers are independent. A language always has a parser;
tags, `enforce` and `lock` each need extra machinery on top.

| Capability | Python | C# | Odin | Lua | Julia | TypeScript | Svelte |
|---|---|---|---|---|---|---|---|
| Parse to model, diagrams, diff | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `rules.yaml` rules — `check` (the model rules) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Constraint tags | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ |
| `enforce` (`tag-conformance`) | ✅ heuristic | ✅ precise | ✅ precise | ✅ idiom-based | ✅ name-based | — | — |
| `lock` (`implementation-locks`) | ✅ `py-ast/1` | ✅ `cs-ts/1` | ✅ `odin-ts/1` | ✅ `lua-ts/1` | ✅ `jl-ts/1` | ❌ | ❌ |
| Reference gate (`reference-architecture`) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Activity / sequence tags | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |

the `tag-conformance` rule and the `implementation-locks` rule refuse an unsupported language **by name** rather than
silently reporting "nothing found", so you always know which of the two you're looking at.

---

## Tag syntax at a glance

The same seven tags, spelled in each language's own idiom. One
[`RuleSpec`](../../src/code_constraints/core/rules.py) row defines all of them, so the
vocabulary can never drift between languages.

| Tag | Python | C# | Julia | Lua / Odin |
|---|---|---|---|---|
| `layer` | `@layer("orders")` | `[Layer("orders")]` | `@layer "orders"` | `@cdec layer("orders")` |
| `sealed` | `@sealed` | `[Sealed]` | `@sealed` | `@cdec sealed` |
| `immutable` | `@immutable` | `[Immutable]` | `@immutable` | `@cdec immutable` |
| `factory` | `@factory(creates=["R"])` | `[Factory(Creates = new[]{"R"})]` | `@factory creates=["R"]` | `@cdec factory(creates = ["R"])` |
| `no-instantiation` | `@no_instantiation(allow=["A"])` | `[NoInstantiation(Allow = new[]{"A"})]` | `@no_instantiation allow=["A"]` | `@cdec no_instantiation(allow = ["A"])` |
| `no-side-effects` | `@no_side_effects` | `[NoSideEffects]` | `@no_side_effects` | `@cdec no_side_effects` |
| `locked` | `@locked(reason="…")` | `[Locked(Reason = "…")]` | `@locked reason="…"` | `@cdec locked(reason = "…")` |

Lua writes the comment as `---@cdec …` and Odin as `//@cdec …`; Lua list arguments use
table braces (`{"A"}`) where Odin uses brackets (`["A"]`). Everything else is identical.

### Why three different carriers

This is the one place the languages genuinely diverge, and it is worth understanding before
you write your first tag.

**Python, C# and Julia have somewhere to hang a no-op.** A decorator, an attribute and a
macro are all real constructs that can be defined to do nothing, so the tag is a shipped
shim you import. Importing it is also the **gate**: a tag counts only when the shim is in
scope, so your own `sealed` decorator is never mistaken for the architectural one.

**Lua and Odin have nowhere.** Lua has no declaration modifiers at all. Odin's `@(...)`
attributes are a *closed set the compiler validates* — a no-op `@(cdec_sealed)` would not
build. Both therefore carry the tag in a namespaced comment sitting exactly where a
decorator would go, and the `@cdec` prefix plays the gating role the import plays elsewhere.

```lua
---@cdec sealed
---@cdec layer("orders")
local Receipt = {}
```

```odin
//@cdec sealed
//@cdec layer("orders")
Receipt :: struct { total: f64 }
```

Annotation blocks require **line adjacency** — a blank line between the comment and the
declaration detaches it. That is deliberate: without it there is no way to tell a
decorator-style tag from a paragraph of prose earlier in the file.

---

## Modelling languages that have no classes

Odin, Lua and Julia have no `class`. All three parsers answer the same two questions the
same way, and the answer determines what your tags actually constrain.

**An operation belongs to its receiver.** In Odin and Julia, functions are declared at
package scope and dispatch on their arguments, so the owner of an operation is **the type of
its first parameter**:

```odin
formatted :: proc(r: ^Receipt) -> string   // → operation `formatted` on Receipt
```

```julia
formatted(r::Receipt)::String              # → operation `formatted` on Receipt
```

Lua differs: a method is written on its table (`function Receipt:formatted()`), so ownership
is lexical and file-scoped.

This is what makes a tag on a free-standing procedure constrain the method a reader expects
to see it on. It also means the same qualified name — `orders.Receipt.formatted` — is what
the diagram shows, what the `implementation-locks` rule records, and what `cdec exceptions allow` accepts.

**Receiver-less callables become a `static` class** named after the file stem, the UML
utility-class idiom. Without it, a tag on a free function would be silently dropped.

---

## Where to go next

- **[Tutorial](../TUTORIAL.md)** — the end-to-end workflow, language-agnostic.
- **[Rules & constraints catalogue](../RULES_CATALOGUE.md)** — every rule and tag in full.
- **[CLI reference](../CLI_REFERENCE.md)** — every command and flag.
- **[Examples](../../examples/README.md)** — the demo projects these guides run against.
