# code-constraints (`cdec`)

**Constrain what changes in a codebase.** `cdec` turns your architectural decisions into
checks that a machine can run. It parses your code into a UML model, shows it as an
interactive class diagram, and fails the build when the code breaks a rule that the team
agreed on. Junior developers, external contributors and coding agents then work inside
those boundaries, not around them.

It supports Python, C#, Odin, Lua, Julia, TypeScript and Svelte 5. It needs Python only —
there is no external binary to install.

## Install

```bash
pip install code-constraints
cdec --help
```

This requires Python 3.11 or later. The package includes the web viewer.
For the MCP server that coding agents use, install `pip install "code-constraints[mcp]"`.

## Quick start

The steps below use a Python project with its code in `src/`. Run every command from the
root of the repository. For other languages, change `--lang` and see the
[per-language guides](docs/languages/README.md).

### 1. Look at the class diagram

```bash
cdec serve parse src
```

This parses `src/`, starts the viewer at http://127.0.0.1:8765, and opens the class
diagram in your browser. `cdec` detects the language. To set it, add `--lang python`.

In the viewer, use the class list to search, show, hide and isolate classes. Click a class
to centre the canvas on it. Press `Ctrl+C` in the terminal to stop the server.

### 2. Create the project config

```bash
cdec init --lang python --source src
```

This writes `.cdec/rules.yaml` (the settings and the rules) and `.cdec/reference.xmi` (a
snapshot of the current architecture). Commit the `.cdec/` folder. The rule list is empty,
so `cdec check` enforces nothing yet.

### 3. Propose a new constraint on the diagram

Export the architecture as a JSON model that you can edit:

```bash
cdec parse src --lang python --out target.json
```

Open `target.json`, find the class, and add a constraint tag to its `rules` list. This
example declares that nothing may subclass `Invoice`:

```json
{
  "name": "Invoice",
  "qualified_name": "myapp.domain.Invoice",
  "rules": [{ "name": "sealed" }],
  ...
}
```

You can also edit the model in the browser. Click **Edit this diagram**, open the
**Code** panel, edit the JSON, and click **Save .json**.

Show the proposal in the viewer, as a diff against the current code:

```bash
cdec propose target.json --focus myapp.domain.Invoice
```

Green shows what the code must add. Red shows what the code must remove. Edit
`target.json` again and run `cdec propose` again: the open browser tab refreshes in place.
When the team agrees, lock the proposal as the target architecture:

```bash
cdec reference set target.json      # writes .cdec/reference.xmi
```

To make the tags in the reference binding, add this rule to `.cdec/rules.yaml`:

```yaml
rules:
  - id: agreed-tags
    type: frozen-rules
    severity: error
```

### 4. Run the check

```bash
cdec check
```

The code does not carry the `@sealed` tag yet, so the check fails with exit code 1:

```
[agreed-tags] (error)
  - [V-34FFDDA4] myapp.domain.Invoice — myapp/domain/invoice.py:12: architectural tag @sealed on 'myapp.domain.Invoice' was removed.

Summary: 1 error(s), 0 warning(s).
```

Every issue starts with a stable key. To accept one issue, give the key and a reason:

```bash
cdec exceptions allow V-34FFDDA4 --reason "agreed in ARCH-42"
```

Put `cdec check` in CI or in a pre-commit hook. A non-zero exit code stops the build.

### 5. Add rules in the config file

Rules that describe the architecture as a whole go in `.cdec/rules.yaml`. Each rule has
an `id`, a `type` and a `severity`. Add a `message` that tells the developer why the rule
exists and how to fix a violation:

```yaml
rules:
  - id: agreed-tags
    type: frozen-rules
    severity: error

  - id: domain-does-not-depend-on-ui
    type: forbidden-package-references
    severity: error
    from: ["myapp.domain.**"]
    to:   ["myapp.ui.**"]
    message: |
      Layering violation: '{source}' must not depend on '{target}'.
      Move the reference to the package that owns the workflow.

  - id: layering
    type: layer-dependencies     # reads the @layer tags from step 6
    severity: error
    allow:
      ui:     [domain]
      domain: []

  - id: tags-must-be-honoured
    type: tag-conformance        # checks the code against its own tags
    severity: error
```

Run `cdec check` again after each change. On an existing codebase, run
`cdec check --automatic-exceptions rules` once to accept the current violations. After
that, only new violations fail. The [rules catalogue](docs/RULES_CATALOGUE.md) lists every
rule type, with its options and a passing and a failing example.

### 6. Add rules in the code with the shims

Rules about one class or one method go in the code, as tags. The tags come from a small
shim module that does nothing at run time. Copy it into the project:

```bash
cdec update-assets --lang python --no-agents     # writes cdec_rules.py
```

Put `cdec_rules.py` where your code can import it. Then tag the code:

```python
from cdec_rules import layer, sealed

@sealed
@layer("domain")
class Invoice:
    ...
```

Run `cdec check` again. The `agreed-tags` rule passes, because the code now carries the
tag from the reference. The `tag-conformance` rule now enforces the tag itself. If a class
subclasses `Invoice`, the check fails:

```
[tags-must-be-honoured] (error)
  - [F-5A5D24E3] myapp.domain.SpecialInvoice — myapp/domain/invoice.py:40: 'myapp.domain.SpecialInvoice' subclasses sealed class 'Invoice'; sealed types may not be subclassed.
```

C# uses attributes (`[Sealed]`), Julia uses macros (`@sealed`), and Lua and Odin use
comments (`---@cdec sealed`, `//@cdec sealed`). See
[the tag table](#architectural-rule-tags) for all tags in all languages.

### Next steps

- Read the [tutorial](docs/TUTORIAL.md) for the full path from the first parse to a
  gated CI pipeline.
- Freeze a function body with `@locked`. See [Implementation locks](#implementation-locks).
- Let a coding agent run the checks. See [Use it from a coding agent](#use-it-from-a-coding-agent-mcp).

---

## How the check works

`cdec check` is the whole gate, and `.cdec/rules.yaml` is the whole contract. Four kinds
of rule run inside it. Each kind answers a different question:

| Rule kind | `type:` | Question it answers |
| --- | --- | --- |
| **Model rules** | `no-new-classes`, `forbidden-references`, `layer-dependencies`, `frozen-rules`, … | Did the *architecture* change? (new or removed classes, forbidden dependencies, cycles, layer violations, weakened tags) |
| **Conformance** | `tag-conformance` | Does the *implementation* obey its tags? (`@no_instantiation`, `@factory`, `@immutable`, `@sealed`) |
| **Freeze** | `implementation-locks` | Did this body change **at all**? (AST digests: reformatted or moved code never trips a lock; a semantic edit does) |
| **Reference gate** | `reference-architecture` | Did *anything* structural change against the committed snapshot? |

Each kind is opt-in. They share the rule catalogue but no logic.

The `rules:` list can also go in `.cdec/rules/*.yaml`, one file per rule set. Then
`cdec check --rules-file NAME` runs a subset — for example, a fast set on every commit and
the full set before a release. Use one layout or the other, not both.

## Architectural rule tags

Python, C# and Julia tags are no-op decorators, attributes and macros from the shim. `cdec`
recognises a tag only when the shim is in scope (`from cdec_rules import …`,
`using CodeConstraints.Rules;`, `using CdecRules`), so unrelated decorators never match.

Lua has no declaration modifiers, and the Odin compiler rejects unknown `@(...)`
attributes. Both languages therefore put the tag in a comment where a decorator would go.
The `@cdec` prefix does the job of the import.

| Tag | Python | C# | Julia | Lua / Odin | Meaning |
| --- | --- | --- | --- | --- | --- |
| no-instantiation | `@no_instantiation(allow=[...])` | `[NoInstantiation(Allow = ...)]` | `@no_instantiation allow=[...]` | `@cdec no_instantiation(allow = [...])` | the body may not construct objects (except the `allow` types) |
| factory | `@factory(creates=[...])` | `[Factory(Creates = ...)]` | `@factory creates=[...]` | `@cdec factory(creates = [...])` | the only place that may build the listed types |
| immutable | `@immutable` | `[Immutable]` | `@immutable` | `@cdec immutable` | fields may not change after construction |
| sealed | `@sealed` | `[Sealed]` | `@sealed` | `@cdec sealed` | the class may not be subclassed |
| layer | `@layer("name")` | `[Layer("name")]` | `@layer "name"` | `@cdec layer("name")` | puts the class in an architectural layer |
| no-side-effects | `@no_side_effects` | `[NoSideEffects]` | `@no_side_effects` | `@cdec no_side_effects` | shown and drift-frozen (body analysis is not implemented yet) |
| locked | `@locked(reason="...")` | `[Locked(Reason = "...")]` | `@locked reason="..."` | `@cdec locked(reason = "...")` | the implementation is frozen — see [Implementation locks](#implementation-locks) |

Lua writes the comment as `---@cdec …` and Odin as `//@cdec …`. ⚠️ Julia macro arguments
are **space-separated**: `@layer "orders"` is correct, and `@layer("orders")` is a syntax
error.

The tags are part of the model. They round-trip through XMI, show as badges on the class
diagram, and take part in the diff. Three decoupled engines enforce them:

- **Model rules.** They read the model and the baseline, never the method bodies.
  `frozen-rules` fails when a tag in the baseline is removed or weakened.
  `layer-dependencies` flags forbidden references between `@layer` tags.
- **`tag-conformance`.** It re-parses the source and inspects method bodies. Detection is
  precise in C# and Odin, heuristic in Python (`allow` is the escape hatch), name-based in
  Julia, and idiom-based in Lua.
- **`implementation-locks`.** It digests the normalised AST of a `@locked` element and
  fails when that AST changes.

To see all of them in one run, try the bundled demo. Its model rules pass, and
`tag-conformance` flags one seeded body violation, so the command exits 1 on purpose:

```bash
cdec check --config examples/python_demo/.cdec --source examples/python_demo
```

## Implementation locks

A locked class or function may not change **at all**. This is stronger than the
architectural rules. Use it to pin down test logic, or an agreed sequence of steps that
nobody may quietly reorder. The rest of the codebase then adapts to the locked code.

The lock applies to the **syntax tree**, not to a range of lines. New code above a locked
function, reformatted code and edited comments change nothing. A renamed local, a swapped
operator, a new statement or two reordered steps fail the check.

**1. Declare the lock in the code.**

```python
from cdec_rules import locked

class Invoice:
    @locked(reason="settlement order agreed with finance")
    def settle(self, amount):
        tax = amount * 0.2
        return amount + tax
```

```csharp
using CodeConstraints.Rules;

[Locked(Reason = "settlement order agreed with finance")]
public decimal Settle(decimal amount) { ... }
```

**2. Turn on the rule** in `.cdec/rules.yaml`:

```yaml
  - id: frozen-implementations
    type: implementation-locks
    severity: error
```

**3. Record the digest.** `cdec check --automatic-exceptions locks` writes the digest to the
`locks:` section of the same file. Commit it.

**4. `cdec check` now enforces the lock.** There is no new CI step:

```
[frozen-implementations] (error)
  NOT EXCEPTABLE: a frozen implementation changes only via
  `cdec check --automatic-exceptions locks --force`.
  - [L-3D246C33] Invoice.settle — billing.py:6: 'Invoice.settle' is a frozen
      method and its implementation changed.
      Lock reason: settlement order agreed with finance
      Locked by: alice on 2026-08-02T10:15:00+00:00
      Revert the change, or ask a lead to approve a re-baseline with
      `cdec check --automatic-exceptions locks --force`.
```

Five conditions fail the check: the body **changed**, the element was **removed**, the
`@locked` tag was deleted (**unlocked**), a tag has no recorded digest (**missing**), or the
digest algorithm changed (**algo-mismatch**). The last one is reported separately, so an
upgrade never looks like tampering.

### Lock code without a tag

To freeze code that you cannot tag, such as a whole test package, give the rule
qualified-name globs:

```yaml
  - id: frozen-implementations
    type: implementation-locks
    severity: error
    include_docstrings: false    # true: docstrings and /// comments count as implementation
    targets:
      - "tests.**"               # every class and function under tests/ is frozen
```

### Keep re-baselining a lead-only action

Anybody can safely run `cdec check --automatic-exceptions locks`. It **adds** locks for new
tags. It never overwrites the digest of a changed implementation, and it never drops an
entry whose tag was deleted. To accept a change, add `--force`:

```bash
cdec check --automatic-exceptions locks --force
```

Only this command rewrites the `locks:` section of `.cdec/rules.yaml`. Put the file behind
a CODEOWNERS entry, and a change to frozen code becomes a reviewed, lead-approved event.
For the same reason, `cdec exceptions allow` refuses an `L-` key, and
`--automatic-exceptions rules` does not accept one.

To ship without a re-baseline, bypass the locks explicitly:

```bash
cdec check --bypass-locks --bypass-reason "hotfix #42"   # or CDEC_LOCK_BYPASS=1
```

A bypassed run prints a banner, still collects every violation, and sets
`summary.bypassed` in `--json-out`. Reject that flag in CI, so that a bypass is always a
deliberate and visible act.

## The review loop: accept known violations

A rule that can only say no gets switched off. `cdec` gives a recorded, reviewable and
revocable way to say "this one is fine":

```bash
cdec check --log-out check.log
#   [no-new-classes] (error)
#     - [V-DD3EA5B2] animals.Cat — animals/cat.py:1: New class 'animals.Cat' was added.

#  …add [ALLOW: agreed in ARCH-42] to the lines that you accept…
cdec exceptions patch --file check.log     # writes .cdec/rules.yaml, with the reason

# or, for one known key:
cdec exceptions allow V-DD3EA5B2 --reason "agreed in ARCH-42"
```

A key is a hash of *what* the issue is (engine, rule, element, detail), never of *where*
it is. An exception therefore survives reformatted and moved code, and the same code
always gives the same key. An agent can run `cdec check --format json`, decide, and call
`cdec exceptions allow <key>` without parsing prose.

Other subcommands: `review`, `remove`, `list`, `prune`. See
[Accepting known violations](docs/CLI_REFERENCE.md#24-accepting-known-violations-cdec-exceptions).

## Use it from a coding agent (MCP)

Any MCP-capable harness (Claude Code, Cursor, VS Code, Windsurf, Zed) can run `cdec` as a
stdio server. The agent then calls the engines as tools and reads structured JSON:

```bash
pip install "code-constraints[mcp]"
```

```json
{
  "mcpServers": {
    "code-constraints": { "type": "stdio", "command": "cdec-mcp", "args": [] }
  }
}
```

Put this in `.mcp.json` at the repository root, or in the equivalent file for your harness
(see the [MCP guide](docs/MCP.md)). The agent gets `cdec_check` for the gate,
`cdec_issues` and `cdec_allow` for the review loop, and `cdec_propose` and
`cdec_reference_set` for the design loop. The issue keys are the same as the keys that the
CLI prints, so an agent and a person can share one workflow.

## Interactive viewer

`cdec serve parse [PATH]` opens the class diagram of a codebase. `cdec serve` starts the
viewer at http://127.0.0.1:8765 without a project. The class diagram gives you:

- **Class list** with search and autocomplete. Click a class to centre the canvas on it.
- **Related classes**: the inheritance and association neighbours of the selected class.
- **Visibility filters**: a checkbox per class, plus Show all, Hide all and Isolate (N hops).
- **Saved views**: export the visible set, positions and selection to a `.cdecview.json`
  file, and import it later.
- **Diff walkthrough**: for a diff, a Prev/Next change list moves the camera to each
  changed class.
- **Rule badges** on tagged classes and operations. Hover a badge to see the rule and its
  parameters.
- **Set as reference** saves the current diagram as `.cdec/reference.xmi`.

Package, activity and sequence diagrams use the same interactive canvas.

The **editor** (click **Edit this diagram**) supports:

- **Visual edits**: add classes, drag between nodes to draw inheritance and associations,
  add attributes and methods, double-click to edit, and press **Delete** to remove a class.
- **Code panel**: the model as editable JSON beside the canvas. An edit on one side updates
  the other. This is the same JSON that `cdec convert` and `cdec propose` use.
- **Live diff**: load a baseline (**Baseline…**, or **Compare vs reference**), and the
  canvas shows added, removed and changed elements while you edit.
- **Open and save** as `.xmi` or `.json`.

## Embedded diagram tags

Mark code regions for activity and sequence diagrams with XML-style comment tags. This
works in Python and C# only:

```python
# <uml-activity name="checkout" granularity="control-flow">
def checkout(cart):
    if cart.is_empty():
        return
    pay(cart)
# </uml-activity>
```

```csharp
// <uml-sequence name="login" root="HandleLogin">
public void HandleLogin(User u) {
    _auth.Verify(u);
    _session.Start(u);
}
// </uml-sequence>
```

Supported tags: `<uml-class />`, `<uml-activity name="..." granularity="control-flow|statement|calls">`,
`<uml-sequence name="..." root="...">`.

## Supported languages

| Language   | `--lang`     | Class / package | Rule tags | `tag-conformance` | `implementation-locks` | Activity / sequence |
| ---------- | ------------ | --------------- | --------- | ----------------- | ---------------------- | ------------------- |
| Python     | `python`     | ✅ | decorators          | ✅ | ✅ | ✅ |
| C#         | `csharp`     | ✅ | attributes          | ✅ | ✅ | ✅ |
| Odin       | `odin`       | ✅ | `//@cdec` comments  | ✅ | ✅ | — |
| Lua        | `lua`        | ✅ | `---@cdec` comments | ✅ | ✅ | — |
| Julia      | `julia`      | ✅ | macros              | ✅ | ✅ | — |
| TypeScript | `typescript` | ✅ | —                   | — | — | — |
| Svelte 5   | `svelte`     | ✅ | —                   | — | — | — |

## Command overview

Each command also runs as `python -m code_constraints.cli <command>`. The
[CLI reference](docs/CLI_REFERENCE.md) documents every option.

| Command | What it does |
| --- | --- |
| `cdec` | Interactive session: setup, viewer, checks, CI scripts. |
| `cdec init` | Scaffold `.cdec/rules.yaml` and a reference snapshot. `--migrate` converts the old per-concern files. |
| `cdec check` | The gate: run every rule and exit non-zero on a violation. |
| `cdec check -A rules\|locks\|reference\|all` | Accept the current state instead of a failure (`--automatic-exceptions`). |
| `cdec exceptions …` | Accept, list, remove and prune individual issues by key. |
| `cdec locks` | Show what is lockable and what is locked (read-only). |
| `cdec serve` / `cdec serve parse` | Start the web viewer / open the class diagram of a codebase. |
| `cdec parse` | Parse source into a model file (`.xmi` or `.json`). |
| `cdec convert` | Convert a model between XMI 2.1 and editor JSON. |
| `cdec propose` | Show a proposed model in the viewer, as a diff. `--against source\|reference\|none`. |
| `cdec reference set` / `show` | Lock a model as the reference / show the code against it. |
| `cdec diff` / `diff-vs-xmi` / `diff-xmi` | Diff two git revisions / source against a model / two models. |
| `cdec update-assets` | Copy the language shim and the bundled Claude agents into a project. |
| `cdec update` | Update a standalone install in place. |

`cdec` also ships two Claude Code agents (`cdec-architect`, `oop-refactor-architect`) and a
skill (`cdec-architecture-loop`). `cdec update-assets` copies them into `.claude/`.

## Documentation

| Document | What it is |
| --- | --- |
| **[Tutorial](docs/TUTORIAL.md)** | **Start here.** From the first parse to a gated CI pipeline, with runnable examples against the bundled demos. |
| **[Rules & constraints catalogue](docs/RULES_CATALOGUE.md)** | Every rule type and every source tag, with options, a sample configuration, and a passing and a failing example. |
| [CLI reference](docs/CLI_REFERENCE.md) | Every command and option, the `.cdec/` files, exit codes and CI/CD recipes. |
| [MCP server](docs/MCP.md) | Install, per-harness configuration and the tool list. |
| **[Per-language guides](docs/languages/README.md)** | [Python](docs/languages/PYTHON.md) · [C#](docs/languages/CSHARP.md) · [Odin](docs/languages/ODIN.md) · [Lua](docs/languages/LUA.md) · [Julia](docs/languages/JULIA.md) · [TypeScript & Svelte](docs/languages/TYPESCRIPT-SVELTE.md) |
| [Examples](examples/README.md) | The demo projects for every language. |
| [Installers](install/README.md) | Standalone install scripts, configuration and uninstall steps. |

---

## Other ways to install

**Standalone installer.** This clones the repository with `git`, manages its own virtualenv,
builds the web frontend, and puts `cdec` on your `PATH`. It requires `git`, Python 3.11+
and Node 20+. To update later, run `cdec update` or run the installer again.

```bash
# Linux / macOS
curl -fsSL https://raw.githubusercontent.com/fleskovar/code_constraints/main/install/install.sh | bash
```

```powershell
# Windows (PowerShell)
irm https://raw.githubusercontent.com/fleskovar/code_constraints/main/install/install.ps1 | iex
```

**From a built wheel:**

```bash
make dist
pip install dist/code_constraints-0.1.0-py3-none-any.whl
```

## Development

The `Makefile` is the front door. `make help` lists every target.

```bash
make setup      # venv + editable install with dev extras + frontend build
make test       # full test suite
make verify     # ruff + mypy + pytest — run before a push
make demo       # run `cdec check` against the bundled examples
make serve      # http://127.0.0.1:8765
```

| Target | What it does |
| --- | --- |
| `make install-dev` | Editable install with dev extras. Code edits take effect immediately. |
| `make install` | Non-editable install from source into the venv. |
| `make install-pipx` | Install the `cdec` CLI globally from this checkout with `pipx`. |
| `make dist` / `make package` | Build the frontend, then the wheel and sdist in `dist/`. The wheel includes the web viewer. |
| `make check-dist` | Build, then validate the artifacts with `twine`. |
| `make frontend-check` | `svelte-check` (TypeScript). |
| `make clean` / `make distclean` | Remove build artifacts and caches / everything generated, `node_modules` included. |

To change the interpreter, the venv or the port, set them on the command line:

```bash
make setup BASE_PYTHON=python3.12 VENV=/tmp/cdec-venv
make serve PORT=9000
```

The recipes run through `sh`. On Windows, use Git Bash or another shell that has `sh` on
`PATH`.

### Frontend

```bash
cd frontend
npm install
npm run dev      # Vite dev server with HMR, proxies /api to :8765
npm run build    # production build into frontend/dist/
npm run check    # svelte-check (TypeScript)
```

Run `cdec serve` and `npm run dev` together. Vite sends `/api/*` to the backend.
`cdec serve` serves the built bundle in `frontend/dist/`. After a frontend edit, run
`npm run build` again, or the server continues to show the old build.
