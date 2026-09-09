# C# MVC demo — layering enforced by tags

A deliberately tiny **Model-View-Controller** app (an in-memory todo list, ~6
classes) that doubles as a **template for new projects**. It's the example that
shows off the `@layer` tag and the `layer-dependencies` rule — the harness's
purpose-built tool for enforcing layered architectures. (The other demos enforce
layering with `forbidden-package-references`; this one uses the tag-driven rule,
which reads the architectural intent straight off the classes.)

Out of the box everything **passes** — copy the folder, point it at your own
code, and start adding classes. The [Try breaking it](#try-breaking-it) section
shows what each guardrail catches.

## The three layers

Each class declares its layer with `[Layer("...")]`. Folder = namespace =
package; the layer name is independent of the package name but kept parallel
here to reinforce the mapping.

| Layer        | Package      | Classes                          | May depend on   |
| ------------ | ------------ | -------------------------------- | --------------- |
| `model`      | `Model`      | `TodoItem`, `TodoRepository`     | *(nothing)*     |
| `view`       | `View`       | `IView`, `TodoConsoleView`       | `model`         |
| `controller` | `Controller` | `IController`, `TodoController`  | `model`, `view` |

```
Controller ───────────► View
    │                     │
    └─────────► Model ◄────┘
```

The arrows only ever point down: a Controller knows the Model and the View; a
View knows the Model; the Model knows nobody. That single invariant is what
`mvc-layer-dependencies` enforces, via the allow-matrix in
[`.cdec/rules.yaml`](.cdec/rules.yaml):

```yaml
allow:
  model: []                 # leaf — references no other layer
  view: [model]
  controller: [model, view]
```

### How the rule "sees" a dependency

`layer-dependencies` reads the structural reference graph — **typed fields and
inheritance bases**, not method-body locals or parameters. So every cross-layer
collaborator is passed in as a constructor-injected `private readonly` field:

- `TodoConsoleView` holds a `TodoRepository` → the allowed **view → model** edge.
- `TodoController` holds a `TodoRepository` **and** an `IView` → the allowed
  **controller → model** and **controller → view** edges.

Note the interfaces (`IView`, `IController`) also carry `[Layer(...)]`. The rule
ignores any target without a layer tag, so tagging the abstraction is what lets
`controller → view` register even though the field is typed as `IView`.

### The other guardrails

- **`controllers-end-in-Controller` / `views-end-in-View`** (`subclass-naming`) —
  any class implementing `IController` / `IView` must be named accordingly, so a
  class's role is obvious at the call site. No new rule was needed: the marker
  interfaces give `subclass-naming` a `base` to match against.
- **`no-cyclic-package-dependencies`** — MVC is acyclic by construction; this
  catches a lower layer that grows a reference back up.
- **`freeze-architectural-tags`** (`frozen-rules`, diff scope) — freezes the
  `[Layer]` / `[Immutable]` / `[Sealed]` tags against `.cdec/reference.xmi`, so a
  silently-deleted constraint is flagged as drift.

`TodoItem` is also `[Immutable]` + `[Sealed]` (get-only properties set once in
the constructor, `WithDone` returns a new instance). Those are
implementation-conformance tags that the separate `cdec enforce` command verifies
against the method bodies.

## Running it

```bash
# Engine A — drift / architecture (model + baseline only). PASSES.
.venv/Scripts/python.exe -m code_constraints.cli check --config examples/csharp_mvc_demo/.cdec --source examples/csharp_mvc_demo

# Engine B — implementation conformance (re-parses bodies). PASSES (TodoItem is
# genuinely immutable and unsubclassed).
.venv/Scripts/python.exe -m code_constraints.cli enforce examples/csharp_mvc_demo --lang csharp

# Visualise: serve and load the folder (language "csharp"). The package diagram
# shows controller → view → model with no cycle; the class diagram shows the
# [layer]/[immutable]/[sealed] badges.
.venv/Scripts/python.exe -m code_constraints.cli serve   # → http://127.0.0.1:8765
```

> The harness only **parses** the C# — there's no `.csproj` and the code isn't
> compiled, so tag recognition needs nothing more than the `using
> CodeConstraints.Rules;` line (the no-op attributes ship in
> `shims/csharp/CodeConstraintsRules.cs`). A real project would add a composition root
> (e.g. `Program.Main`) that `new`s up the repository, view, and controller and
> wires them together — the one place construction is expected, sitting above all
> three layers.

## Try breaking it

Each edit below trips exactly the rule named, then `cdec check` goes green again
when you revert it — the fastest way to feel what the guardrails do.

1. **Reverse a dependency arrow.** Add a controller reference to the model — in
   `Model/TodoRepository.cs`, add `using Controller;` and a field
   `private TodoController _ctrl;`. Re-run `cdec check`: **`mvc-layer-dependencies`**
   fires (model may depend on nothing) *and* **`no-cyclic-package-dependencies`**
   fires (Controller ↔ Model is now a cycle).

2. **Break a naming convention.** Add a class
   `public class TodoManager : IController` under `Controller/`. **`controllers-end-in-Controller`**
   fires: an `IController` implementer must end in `Controller`.

3. **Drop an architectural tag.** Delete `[Layer("model")]` from `TodoItem`.
   **`freeze-architectural-tags`** fires — the tag recorded in
   `reference.xmi` is gone. (Run `cdec check --update-reference` to *deliberately*
   accept a new baseline.)

## Using this as a template

1. Copy `examples/csharp_mvc_demo/` to your project root (keep the `.cdec/`
   folder).
2. Rename the layers in `.cdec/rules.yaml`'s allow-matrix to match your
   architecture (e.g. `domain` / `application` / `infrastructure`), and update the
   `[Layer(...)]` tags to match.
3. Pass every cross-layer collaborator as a constructor-injected typed field so
   the rule can see it.
4. Run `cdec check --update-reference` once to snapshot your starting point, then
   `cdec check` in CI.
