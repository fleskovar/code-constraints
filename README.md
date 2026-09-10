# code-constraints (`cdec`)

**Constrain what changes in a codebase.** `cdec` lets a team encode its architectural and
implementation decisions as machine-checkable constraints, then enforces them in CI and in
the day-to-day development loop — so junior developers, external contributors, and coding
agents work inside the boundaries the team agreed on instead of around them.

**One file, one command.** Everything a project commits lives in `.cdec/rules.yaml`, and
`cdec check` is the whole gate. Four kinds of rule run inside it, answering four different
questions:

| Rule kind | `type:` | Question it answers |
| --- | --- | --- |
| **Model rules** | `no-new-classes`, `forbidden-references`, `layer-dependencies`, … | Did the *architecture* change? (new/removed classes, forbidden dependencies, cycles, layer violations, weakened tags) |
| **Conformance** | `tag-conformance` | Does the *implementation* obey its tags? (`@no_instantiation`, `@factory`, `@immutable`, `@sealed`) |
| **Freeze** | `implementation-locks` | Did this body change **at all**? (AST-identity digests — reformatting and moving code never trip a lock; any semantic edit does) |
| **Reference gate** | `reference-architecture` | Has *anything* structural changed against the committed snapshot? |

Each one is opt-in, and they share a rule catalogue but no logic. `cdec check` exits
non-zero on violation, so it drops straight into a CI/CD pipeline or a pre-commit hook:

```yaml
# .cdec/rules.yaml — the whole contract
language: python
source: src

rules:
  - id: domain-is-a-leaf-package
    type: forbidden-package-references
    severity: error
    from: ["myapp.domain.**"]
    to:   ["myapp.ui.**"]
    message: |
      Layering violation: '{source}' must not depend on '{target}'.
      Move the reference to whichever package owns the workflow.

  - id: tags-must-be-honoured
    type: tag-conformance
    severity: error

  - id: frozen-implementations
    type: implementation-locks
    severity: error
```

```bash
cdec check
```

Underneath the constraint layer sits a full **UML modelling pipeline** — it is how the tool
knows what your architecture *is*. `cdec` parses **Python, C#, Odin, Lua, Julia, TypeScript, and Svelte 5**
into a UML model, persists it as XMI 2.1 (or editor JSON), renders class / package /
activity / sequence diagrams, diffs any two revisions, and serves an interactive browser
canvas for reviewing and editing the target architecture before locking it in.

The interactive canvas is built on [SvelteFlow](https://svelteflow.dev/) (`@xyflow/svelte`) with [dagre](https://github.com/dagrejs/dagre) auto-layout. Sequence diagrams still render via the static Graphviz SVG path.

## Install (standalone)

The fastest way to get a working `cdec` command system-wide. These installers use your
existing `git` to clone the project, create and manage their own Python virtualenv, build
the web frontend, and put `cdec` on your PATH. **Re-running the installer updates** to the
latest `main` (re-syncing dependencies and rebuilding the frontend).

**Linux / macOS:**
```bash
curl -fsSL https://raw.githubusercontent.com/fleskovar/code_constraints/main/install/install.sh | bash
```

**Windows (PowerShell):**
```powershell
irm https://raw.githubusercontent.com/fleskovar/code_constraints/main/install/install.ps1 | iex
```

Requires `git`, Python 3.11+, and Node 20+. See [`install/`](install/) for configuration
(install location, repo URL, branch) and uninstall steps. For developing **on**
code-constraints itself, use the in-repo `scripts/bootstrap.{ps1,sh}` instead.

To **update** later, run `cdec update` (or just re-run the installer) — it pulls the latest
code, re-syncs dependencies, and rebuilds the web UI.

## Quick start

From a clone, the `Makefile` is the shortest path — it creates the venv, installs
`code-constraints` in editable mode with dev extras, and builds the frontend:

```bash
make setup      # venv + editable install + frontend build
make test       # full test suite
make demo       # run `cdec check` against the bundled examples
make serve      # http://127.0.0.1:8765
make help       # every target
```

Or do it by hand:

```bash
pip install -e ".[dev]"

# (one-time) build the frontend so `cdec serve` has something to mount
cd frontend && npm install && npm run build && cd ..

# Parse a project to XMI
cdec parse path/to/code --lang python --out project.xmi

# Render a single diagram to SVG (one-shot, no browser)
cdec render project.xmi --diagram class -o class.svg

# Diff two git revisions
cdec diff main feature --lang python --out diff.xmi
cdec render diff.xmi --diagram class -o class-diff.svg

# Launch the interactive web viewer at http://127.0.0.1:8765
cdec serve
```

Everywhere a model file is read or written (`parse --out`, `render`, `diff*`, `reference *`,
`convert`) both **XMI 2.1** (`.xmi`) and **editor JSON** (`.json`) are accepted — the JSON
shape is the same document the web editor and the proposal endpoint use, and is far easier
for humans and AI agents to author than XMI.

## Documentation

| Document | What it is |
| --- | --- |
| **[Tutorial](docs/TUTORIAL.md)** | **Start here.** A guided path from parsing your first codebase to a fully gated CI pipeline — every example runnable against the bundled demos. Covers every rule type, the design loop, CI recipes, and per-language specifics. |
| **[Rules & constraints catalogue](docs/RULES_CATALOGUE.md)** | Every constraint the tool can enforce, in one place — each `rules.yaml` rule type and each source tag with its options, a sample configuration, and a passing *and* failing example. The reference for developers and architects deciding what to encode. |
| [CLI reference](docs/CLI_REFERENCE.md) | Exhaustive reference: every command and option, the `.cdec/` config files, exit codes, and CI/CD recipes. |
| [MCP server](docs/MCP.md) | Run code-constraints as a stdio MCP server so a coding agent calls the engines as tools. Install, per-harness configuration, and the tool surface. |
| **[Per-language guides](docs/languages/README.md)** | One complete walk-through per language — how it maps onto the UML model, how its tags are spelled, what each engine can see, and its parser gotchas. [Python](docs/languages/PYTHON.md) · [C#](docs/languages/CSHARP.md) · [Odin](docs/languages/ODIN.md) · [Lua](docs/languages/LUA.md) · [Julia](docs/languages/JULIA.md) · [TypeScript & Svelte](docs/languages/TYPESCRIPT-SVELTE.md) |
| [Examples](examples/README.md) | The demo projects — Python, C#, C# MVC, Odin, Lua, Julia, TypeScript, Svelte. |
| [Installers](install/README.md) | Standalone install scripts, configuration, and uninstall steps. |

If you are new, read the tutorial's [Part 3](docs/TUTORIAL.md#part-3--your-first-guardrail)
first — it is the shortest path from "installed" to "CI rejects bad PRs". When you are
deciding *which* constraints to turn on, work from the
[rules & constraints catalogue](docs/RULES_CATALOGUE.md).

## Propose → review → lock workflow

The fluent way to plan architectural changes with an agent (or by hand):

```bash
# 1. Get an editable model of the current architecture
cdec parse src/ --lang python --out target.json     # (or: cdec convert .cdec/reference.xmi target.json)

# 2. Edit target.json (you or your AI agent) to describe the target architecture

# 3. Push it to the viewer, diffed against the current code
cdec propose target.json --focus billing.Invoice,billing.PaymentGateway
#    green = the code still needs to grow this, red = to be removed.
#    Re-running `cdec propose` after more edits REFRESHES the open browser tab
#    in place (no new tabs) — iterate: edit → propose → discuss → repeat.

# 4. Once agreed, lock it as the target architecture
cdec reference set target.json                      # writes .cdec/reference.xmi

# 5. Constrain development against it
cdec check        # CI gate: exit 1 on structural deviation
cdec check                 # architectural drift rules vs the same reference
```

`cdec propose` reuses an already-running `cdec serve` on the same port (pushing over HTTP;
any open viewer tab hot-swaps via polling) or starts one with the proposal pre-loaded.
`--against reference` diffs against the locked reference instead of the current source;
`--focus A,B` pre-filters the class canvas to the classes under discussion.

## Use it from a coding agent (MCP)

The same workflow is available to any MCP-capable harness — Claude Code, Cursor, VS Code,
Windsurf, Zed — as a stdio server, so an agent runs the engines as tools and reads
structured JSON instead of parsing CLI output:

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

Drop that in `.mcp.json` at your repo root (or the equivalent file for your harness — see
the [MCP guide](docs/MCP.md)). The agent gets `cdec_check` / `cdec_check` /
`cdec_check` for the gate, `cdec_issues` + `cdec_allow` for the review loop,
and `cdec_propose` + `cdec_reference_set` for the design loop. Issue keys are identical to
the ones the CLI prints, so the two interfaces are interchangeable mid-workflow.

## Evolving the rules: the review loop

Constraints only stay switched on if there is a sane way to say "yes, this one is fine".
Every issue the engines report leads with a stable key, and accepting it is a recorded,
reviewable, revocable decision:

```bash
cdec check --log-out check.log
#   [no-new-classes] (error)
#     - [V-DD3EA5B2] animals.Cat — animals/cat.py:1: New class 'animals.Cat' was added.

#  …mark the lines you accept — add [ALLOW: agreed in ARCH-42] anywhere on them…
cdec exceptions patch --file check.log     # → .cdec/rules.yaml, with the reason attached

# or, when you already know which one you mean:
cdec exceptions allow V-DD3EA5B2 --reason "agreed in ARCH-42"
```

Keys are hashes of *what* an issue is — engine, rule, element, discriminator — never of
where it sits, so a waiver survives reformatting and moved code, and the same code always
produces the same key. That last property is what makes the loop scriptable: an agent can
run `cdec check --format json`, decide, and call `cdec exceptions allow <key>` with no prose
parsing in between.

See [Accepting known violations](docs/CLI_REFERENCE.md#24-accepting-known-violations-cdec-baseline)
for the full command set (`review`, `patch`, `allow`, `remove`, `list`, `prune`).

`cdec serve` mounts `frontend/dist/` at `/`. If you edit the frontend, rerun `npm run build` to refresh the bundle — otherwise the server keeps serving the stale build.

## Supported languages

| Language    | `--lang`     | Class / package | Activity / sequence tags | Rule tags (badges, drift, enforce) |
| ----------- | ------------ | --------------- | ------------------------ | ---------------------------------- |
| Python      | `python`     | ✅              | ✅                       | ✅                                 |
| C#          | `csharp`     | ✅              | ✅                       | ✅                                 |
| TypeScript  | `typescript` | ✅              | —                        | —                                  |
| Svelte 5    | `svelte`     | ✅              | —                        | —                                  |

Activity/sequence comment tags and architectural rule tags are currently recognised in `.py` and `.cs` sources only. TypeScript and Svelte parse to class + package diagrams.

## Interactive session

Run `cdec` with no arguments to enter the interactive session. It auto-detects the project language, walks you through first-time setup if needed, then offers a menu:

```
🌐  Launch the web app (interactive diagrams)
🔍  Run architectural checks (cdec check + enforce)
🧪  Run the project test suite
📦  Generate CI/CD scripts (Windows + Linux)
🔄  Update project assets (agents, shims)
```

**First-time setup** scaffolds `.cdec/` (config, rule templates, reference XMI), copies the bundled Claude agents into `.claude/agents/`, and copies the language rule shims.

**Update project assets** re-installs the Claude agents and shims from the version of code-constraints currently installed. Run this after upgrading to pick up new agents or shim changes without re-initialising the whole project.

## Bundled Claude agents & skill

code-constraints ships two Claude Code agents and one skill. Deploy them into your project's `.claude/` folder with **`cdec update-assets`** (which also installs the language rule shim), or via the prompts in the interactive `cdec` session — note that `cdec init` scaffolds `.cdec/` only:

| Asset | Trigger |
| ----- | ------- |
| `cdec-architect` (agent) | Design new features — translates specs into UML class diagrams, proposes design patterns, defines architectural constraints, and drives the propose → review → lock workflow with `.json`/`.xmi` model files. |
| `oop-refactor-architect` (agent) | Analyse an existing codebase's class structure and produce actionable refactoring proposals: simplification, decoupling, layer proposals, and code-constraints rule/constraint suggestions. |
| `cdec-architecture-loop` (skill) | Interactive architecture discussions — teaches any Claude session the propose → review → lock loop: author a JSON model, `cdec propose` it into the browser diffed against the code, iterate through chat while the open tab refreshes, then lock with `cdec reference set`. |

Once deployed, the agents are available in any Claude Code session on the project via the `/agents` command or by mentioning them by name; the skill activates automatically when an architecture discussion starts (or explicitly via `/cdec-architecture-loop`).

## CLI reference

All commands are also runnable as `python -m code_constraints.cli <command>` if the `cdec` entry point isn't on your `$PATH`.

### `cdec parse`
Parse a source tree and write a model file (`.xmi` for XMI 2.1, `.json` for editor JSON).
```bash
cdec parse PATH --lang {python|csharp|odin|lua|julia|typescript|svelte} --out project.xmi  # or .json
```

### `cdec convert`
Convert a model file between XMI 2.1 and editor JSON (either direction).
```bash
cdec convert model.xmi model.json
cdec convert model.json model.xmi
```

### `cdec propose`
Push a proposed target architecture to the web viewer, diffed against a baseline
(default: the current source; `--against reference` for the locked reference;
`--against none` to render it standalone). Re-running refreshes any open viewer
tab in place. See the "Propose → review → lock" section above.
```bash
cdec propose target.json [--source SRC] [--lang LANG] [--against {source|reference|none}]
            [--focus Qname1,Qname2] [--port 8765] [--no-browser]
```

### `cdec reference`
Manage the locked target architecture (`.cdec/reference.xmi`).
```bash
cdec reference set target.json     # lock an authored model (.json or .xmi) as the reference
cdec check --automatic-exceptions reference [SOURCE]     # re-snapshot the reference from the current code
cdec check [SOURCE]       # CI gate: exit 1 if code deviates structurally
cdec reference show [SOURCE]       # open the viewer on a code-vs-reference diff
```

### `cdec render`
Render an SVG from a stored XMI file. Needs Graphviz `dot`. `--name` is required for `activity`/`sequence`.
```bash
cdec render project.xmi --diagram {class|package|activity|sequence} [--name NAME] -o out.svg
```

### `cdec diff`
Diff two git revisions and emit an annotated XMI (added/removed/changed). Checks out both refs into a temp dir, never touching the working tree.
```bash
cdec diff OLD_REF NEW_REF --lang LANG --out diff.xmi [--repo .] [--subpath SUBDIR]
```

### `cdec diff-vs-xmi`
Parse a source tree and diff it against a previously-saved reference XMI (the reference is the OLD side, source is NEW).
```bash
cdec diff-vs-xmi reference.xmi SOURCE_PATH --lang LANG --out diff.xmi
```

### `cdec diff-xmi`
Diff two already-parsed XMI files (e.g. CI artefacts from two branches) without re-parsing source. Both must share the same `source_language`.
```bash
cdec diff-xmi old.xmi new.xmi --out diff.xmi
```

### `cdec init`
Scaffold a `.cdec/` folder (config, rule templates, baseline, and a reference XMI snapshot) for `cdec check`.
```bash
cdec init [--config .cdec] [--lang python] [--source .] [--force]
```

### `cdec update-assets`
Update the Claude agents and language shims to the version bundled with the currently-installed code-constraints. Run after upgrading to pick up new agents or shim changes in an existing project. Language is auto-detected from `.cdec/rules.yaml` when `--lang` is omitted.
```bash
cdec update-assets [--project-root .] [--lang LANG] [--no-agents] [--no-shims]
```

### `cdec update`
Update the installation in place — equivalent to re-running the standalone installer. Pulls the latest code from GitHub, re-syncs Python dependencies (picking up requirement changes), and rebuilds the web frontend. The refreshed code takes effect on the next `cdec` invocation. Works on installs created by the standalone installer or a git clone.
```bash
cdec update [--branch BRANCH] [--no-frontend]
```

### `cdec check`  — the gate
Run every rule in `.cdec/rules.yaml`. Exits non-zero on any violation at or above
`--fail-on` severity (default `error`). This is the only enforcement command; the rule
types in that file decide what it actually does.
```bash
cdec check [--config .cdec] [--source SRC] [--lang LANG]
           [--reference model.xmi | --base-ref GIT_REF] [--repo .]
           [--format {human|json}] [--json-out report.json] [--log-out check.log]
           [--fail-on {error|warning|none}]
           [--automatic-exceptions {rules|locks|reference|all}]  # accept the current state
           [--force]                                 # with `locks`: accept a CHANGED body
           [--bypass-locks --bypass-reason "..."]    # report lock violations without failing
```

`--automatic-exceptions` is how you accept the code as it stands rather than failing on it:

| Value | Effect |
| --- | --- |
| `rules` | Grandfather every current violation into `exceptions:` — the adoption move on an existing codebase. Only **new** violations fail afterwards. |
| `locks` | Record digests for newly `@locked` code. Safe for anyone: without `--force` it only *adds*. |
| `reference` | Re-snapshot `.cdec/reference.xmi` from the current source. |
| `all` | All three. |

```bash
cdec locks [SRC] [--all] [--json]    # read-only: what is lockable / locked, and its state
```

### `cdec exceptions`  — accept known violations (the review loop)
Every issue the engines report carries a stable key (`V-` check, `F-` enforce, `L-` lock). Quote the key to accept an issue as known-and-allowed, with a reason, recorded in the `exceptions:` section of `.cdec/rules.yaml`. Keys are derived from *what* the issue is, not where — so a waiver survives reformatting and moved code.
```bash
cdec exceptions review --out review.txt   # one markable line per issue
#  …add [ALLOW] (or [ALLOW: reason]) to the lines you accept…
cdec exceptions patch --file review.txt   # apply exactly those; `--file -` reads stdin

cdec exceptions allow V-DD3EA5B2 --reason "agreed in ARCH-42"   # or name keys directly
cdec exceptions remove V-DD3EA5B2         # withdraw: the issue blocks again
cdec exceptions list                      # what's accepted, and why
cdec exceptions prune                     # drop waivers whose issue is gone
```
`cdec check --log-out check.log` output is directly patchable — the parser just needs a marker and a key on the same line. Lock violations (`L-`) are **not** waivable this way: a frozen implementation is re-baselined with `cdec check --automatic-exceptions locks --force`, which leaves its own reviewable diff.

### `cdec serve`
Run the local web viewer (FastAPI + Svelte SPA). Default port is **8765**.
```bash
cdec serve [--host 127.0.0.1] [--port 8765]
```

## Interactive viewer

After `cdec serve`, open http://127.0.0.1:8765 and register a project path. The class diagram view gives you:

- **Class list panel** with search + autocomplete; click a class to centre the canvas on it.
- **Related classes** sub-list showing inheritance and association neighbours of the selected class.
- **Visibility filtering** — per-class checkboxes plus Show all / Hide all / Isolate (with N-hop traversal).
- **Saved views** — Export the current visible set, drag positions, and selection to a `.cdecview.json` file; Import to restore them later.
- **Diff walkthrough** — when viewing a diff XMI, a Prev/Next change list appears that pans the camera to each affected class.
- **Rule badges** — tagged classes/operations carry colour-coded badges (hover for the rule + parameters); badge changes participate in the diff styling.

Package and activity diagrams also render interactively. Sequence diagrams remain on the static SVG path.

### Editing diagrams in the browser

The **editor** (Home → editor, or "Edit this diagram" on any parsed view) supports:

- **Visual editing** — "+ Add class", drag between nodes to draw inheritance/associations,
  hover a class for quick "+ attribute" / "+ method" buttons, double-click to edit in a
  form, and press **Delete** to remove the selected class.
- **Code panel** — the "Code" toggle opens the model as editable JSON side-by-side with
  the canvas; typing in either side updates the other (same JSON that `cdec convert` /
  `cdec propose` consume).
- **Live baseline diff** — load a baseline (`Baseline…` file button, or "Compare vs
  reference" when editing a parsed project) and the canvas shows added/removed/changed
  styling *while you edit* — simultaneous edit + diff preview.
- **Open / save** both `.xmi` and `.json`; "Set as reference" locks the edited model as
  the project's target architecture.

## Architectural rule tags & the three enforcement engines

Tag classes and methods with design constraints using **Python decorators / C# attributes / Julia macros**, all shipped as no-op shims so tagged code still imports and compiles. A tag is only recognised when the shim is in scope (`from cdec_rules import …` / `using CodeConstraints.Rules;` / `using CdecRules`), so unrelated decorators never false-match.

**Lua and Odin have no construct to hang a no-op on** — Lua has no declaration modifiers, and the Odin compiler rejects unknown `@(...)` attributes — so both carry tags in a namespaced annotation comment placed where a decorator would go (`---@cdec sealed` / `//@cdec sealed`), with the `@cdec` prefix playing the gating role the import plays elsewhere.

| Tag | Python | C# | Julia | Lua / Odin | Meaning |
| --- | --- | --- | --- | --- | --- |
| no-instantiation | `@no_instantiation(allow=[...])` | `[NoInstantiation(Allow = ...)]` | `@no_instantiation allow=[...]` | `@cdec no_instantiation(allow = [...])` | the body may not construct objects (except `allow`-listed types) |
| factory | `@factory(creates=[...])` | `[Factory(Creates = ...)]` | `@factory creates=[...]` | `@cdec factory(creates = [...])` | the only place allowed to build the listed types |
| immutable | `@immutable` | `[Immutable]` | `@immutable` | `@cdec immutable` | fields may not be reassigned after construction |
| sealed | `@sealed` | `[Sealed]` | `@sealed` | `@cdec sealed` | the class may not be subclassed |
| layer | `@layer("name")` | `[Layer("name")]` | `@layer "name"` | `@cdec layer("name")` | assigns the class to an architectural layer |
| no-side-effects | `@no_side_effects` | `[NoSideEffects]` | `@no_side_effects` | `@cdec no_side_effects` | captured + visualised + drift-frozen (body analysis deferred) |
| locked | `@locked(reason="...")` | `[Locked(Reason = "...")]` | `@locked reason="..."` | `@cdec locked(reason = "...")` | the implementation is frozen — see [Implementation locks](#implementation-locks) |

Lua writes the comment as `---@cdec …` and Odin as `//@cdec …`. ⚠️ Julia macro arguments are **space-separated** — `@layer "orders"` is correct, `@layer("orders")` is a syntax error. Full detail per language: **[language guides](docs/languages/README.md)**.

The tags are captured on the model, round-trip through XMI, render as badges in the web class diagram, and participate in the diff. **Enforcement is split into three completely decoupled engines** sharing only the rule catalog:

- **Model rules (drift / architectural).** Model + baseline only, never read bodies. `frozen-rules` fails when a baseline tag is removed or weakened; `layer-dependencies` flags forbidden cross-layer references from `@layer` tags.
- **`tag-conformance` (implementation conformance).** Re-parses source ASTs and inspects method bodies. Detection is precise in C# and Odin (grammar node kinds), heuristic in Python (`allow` is the escape hatch), name-based in Julia, and idiom-based in Lua.
- **`implementation-locks` (implementation freeze).** Digests the normalised AST of a `@locked` element and fails if it changes at all.

The three are separate engines internally and share only the rule catalogue — the rule
types are thin adapters, so `cdec check` gives one report without coupling them.

```bash
# One command runs every rule the demo configures. Its model rules pass — the
# architecture is intact — and its `tag-conformance` rule flags the one seeded
# body violation, so this exits 1 on purpose.
cdec check --config examples/python_demo/.cdec --source examples/python_demo
```

See [`examples/`](examples/) for small bookstore codebases (Python, C#, Odin, Lua, Julia, TypeScript, Svelte); the Python, C#, Odin, Lua and Julia demos each carry a fully-worked tagged `billing` slice with one intentional violation.

## Implementation locks

A locked class or function may not change **at all**. This is stronger than the architectural rules above: it is how you pin down test logic, or a sequence of steps that has been agreed and must not be quietly reordered, and force the rest of the codebase to adapt to it rather than the other way round.

The lock is over the **syntax tree**, not a range of lines. Adding code above a locked function, reformatting it, rewrapping an expression, or editing comments changes nothing. Renaming a local, swapping an operator, adding a statement, or reordering two steps fails the check.

**1. Declare the lock in code.**

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

**2. Turn the rule on** in `.cdec/rules.yaml`:

```yaml
  - id: frozen-implementations
    type: implementation-locks
    severity: error
```

**3. Baseline it.** `cdec check --automatic-exceptions locks` records the digest in the
`locks:` section of the same file — commit it.

**4. It is now enforced by `cdec check`**, so there is no new CI step:

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

Five things fail the check, covering every way a freeze can be undone: the body **changed**, the element was **removed**, the `@locked` tag was deleted (**unlocked**), a tag was never baselined (**missing**), and the digest algorithm changed (**algo-mismatch**, reported separately so an upgrade never looks like tampering).

### Locking without decorating

To freeze code you can't practically tag — a whole test package, say — give the rule qualified-name globs:

```yaml
  - id: frozen-implementations
    type: implementation-locks
    severity: error
    include_docstrings: false    # count docstrings / /// comments as implementation
    targets:
      - "tests.**"               # every class and function under tests/ is frozen
```

### Keeping re-baselining a lead-only action

`cdec check --automatic-exceptions locks` is safe for anyone to run: it **adds** locks for newly tagged elements but will never overwrite the digest of an implementation that has drifted, and never drops an entry whose tag was deleted. Accepting a change requires `--force`:

```bash
cdec check --automatic-exceptions locks --force
```

That is the only path that rewrites the `locks:` section of `.cdec/rules.yaml`, so putting the file behind a CODEOWNERS entry makes approving a change to frozen code a reviewable, lead-gated event. `cdec exceptions allow` refuses an `L-` key for the same reason, and `--automatic-exceptions rules` will not grandfather one either.

To ship without re-baselining, bypass explicitly:

```bash
cdec check --bypass-locks --bypass-reason "hotfix #42"   # or CDEC_LOCK_BYPASS=1
```

A bypassed run prints a banner, still collects every violation, and sets `summary.bypassed` in `--json-out` — reject that flag in CI to keep bypassing a deliberate, visible act.

## Requirements

- Python 3.11+
- [Graphviz](https://graphviz.org/download/) — the `dot` binary must be on `$PATH` (or set `$CDEC_DOT_BIN` to point at it). Needed for `cdec render` and the sequence-diagram fallback in the web viewer. `parse`, `diff`, `check`, and `enforce` do not need it.
- Node 20+ for building / iterating on the frontend.

## Frontend development

```bash
cd frontend
npm install
npm run dev      # Vite dev server with HMR, proxies /api to :8765
npm run build    # production build into frontend/dist/
npm run check    # svelte-check (TypeScript)
```

Run `cdec serve` and `npm run dev` together when iterating; Vite proxies `/api/*` to the backend.

## Embedded diagram tags

Authors can mark code regions for activity and sequence diagrams using XML-style comment tags (Python and C# only — Odin, Lua and Julia have parsers and tags but no activity/sequence support yet):

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

Supported tags: `<uml-class />`, `<uml-activity name="..." granularity="control-flow|statement|calls">`, `<uml-sequence name="..." root="...">`.

## Testing

```bash
make install-dev                         # or: pip install -e ".[dev]"
make test                                # or: pytest
pytest tests/test_python_parser.py       # one file
make verify                              # ruff + mypy + pytest
make frontend-check                      # svelte-check (TypeScript)
```

## Building & installing

Every development and packaging flow has a `make` target (`make help` lists them all):

| Target | What it does |
| --- | --- |
| `make setup` | One-time dev environment: venv, editable install with dev extras, frontend deps + build. |
| `make install-dev` | Editable install with dev extras — the **development version**. Code edits take effect immediately. |
| `make install` | Non-editable **install from source** into the venv. |
| `make install-pipx` | Install the `cdec` CLI **globally** from this checkout via `pipx`. |
| `make dist` / `make package` | Build the frontend, then produce the wheel + sdist in `dist/`. |
| `make check-dist` | Build, then validate the artifacts with `twine`. |
| `make verify` | `ruff` + `mypy` + `pytest` — the gate to run before pushing. |
| `make clean` / `make distclean` | Remove build artifacts and caches / everything generated including `node_modules`. |

Override the interpreter or venv location on the command line:

```bash
make setup BASE_PYTHON=python3.12 VENV=/tmp/cdec-venv
make serve PORT=9000
```

Installing the built wheel elsewhere:

```bash
make dist
pip install dist/code_constraints-0.1.0-py3-none-any.whl
cdec --help
```

> **Note:** the wheel bundles the Python packages, the rule shims, and the Claude assets,
> but **not** `frontend/dist`. An installed wheel serves the API and a JSON placeholder at
> `/` rather than the SPA — use a clone (or the standalone installer above) if you want the
> web viewer.

Recipes run through `sh`. On Windows use Git Bash, or any shell that provides `sh` on
`PATH`, so the venv-layout detection works.
