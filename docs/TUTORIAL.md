# code-constraints Tutorial

A guided path from "I have a codebase" to "my CI rejects pull requests that violate our
architecture." Every section is runnable against the demo projects bundled in this
repository, so you can follow along before pointing the tool at your own code.

Work through it in order — each part builds on the last — or jump to the part that matches
what you need today.

| Part | You will learn | Needs config? |
|---|---|---|
| [0. Setup](#part-0--setup) | Getting `cdec` installed | — |
| [1. See what you have](#part-1--see-what-you-have) | `parse`, `serve`, `render` | No |
| [2. See what changed](#part-2--see-what-changed) | `diff`, `diff-vs-xmi`, `diff-xmi` | No |
| [3. Your first guardrail](#part-3--your-first-guardrail) | `init`, `.cdec/rules.yaml`, `check`, `exceptions` | Yes |
| [4. The rule catalogue](#part-4--the-rule-catalogue) | Dependency, layer, and shape rules | Yes |
| [5. Tagging code with constraints](#part-5--tagging-code-with-constraints) | Rule tags + `tag-conformance` | Tags |
| [6. Freezing implementations](#part-6--freezing-implementations) | `implementation-locks` | Tags |
| [7. The reference gate](#part-7--the-reference-gate) | `reference-architecture` — the strict backstop | Yes |
| [8. Designing before you build](#part-8--designing-before-you-build) | JSON models, `propose` → `reference set` | Yes |
| [9. Wiring up CI/CD](#part-9--wiring-up-cicd) | GitHub Actions, GitLab, pre-commit | Yes |
| [10. Constraining AI agents](#part-10--constraining-ai-agents-and-new-contributors) | The bundled agents + guardrail strategy | Yes |
| [11. Language specifics](#part-11--language-specifics) | Python, C#, Odin, Lua, Julia, TypeScript, Svelte | — |
| [12. Troubleshooting](#part-12--troubleshooting) | Common failures and fixes | — |

> **One command, one file.** Everything from Part 3 onward is configured in
> `.cdec/rules.yaml` and checked by `cdec check`. Architectural rules, source-tag
> conformance, implementation locks and the reference gate are all `type:` values in
> that one file, so CI runs one command and reads one exit code. Parts 5, 6 and 7
> add a rule type each; they do not add a command.

> **Looking for the full list of what you can enforce?** Parts 4–6 introduce the rules and
> tags as you need them. The complete, per-rule reference — every option, a sample
> configuration, and a passing *and* failing example for each — lives in the
> **[Rules & constraints catalogue](RULES_CATALOGUE.md)**.

> **Conventions.** Examples use the `cdec` console script. If it is not on your `PATH`, use
> `python -m code_constraints.cli …` instead — the two are interchangeable. Commands are run
> from the repository root unless stated otherwise.

---

## Part 0 — Setup

### From a clone (recommended while learning)

```bash
git clone <your-fork-or-clone-url> code-constraints
cd code-constraints
make setup
```

`make setup` creates `.venv/`, installs `code-constraints` in editable mode with dev extras,
and builds the web frontend. Verify:

```bash
make test          # 319 tests should pass
cdec --help
```

`make help` lists every target (`install-dev`, `install`, `install-pipx`, `dist`, `verify`,
`demo`, `serve`, `clean`, …).

### Just the CLI, globally

```bash
pipx install .          # or: make install-pipx
cdec --help
```

### Requirements

- **Python 3.11+** — required.
- **Node 20+** — only to build the web viewer.
- **Graphviz** (`dot` on `PATH`, or `$CDEC_DOT_BIN`) — only for `cdec render` and sequence
  diagrams in the viewer. Parsing, diffing, and *all four enforcement engines* work
  without it.

> The web viewer defaults to port **8765**, not 8000 — port 8000 is reserved by `http.sys`
> on many Windows machines. Override with `--port`.

---

## Part 1 — See what you have

**Goal:** understand an unfamiliar codebase's structure without changing anything. No
configuration is needed for this part.

### 1.1 Parse a codebase into a model

```bash
cdec parse examples/python_demo --lang python --out demo.xmi
```

```
wrote demo.xmi
```

`demo.xmi` is an **XMI 2.1** document — the on-disk source of truth. It contains packages,
classes, attributes, operations, inheritance, and any architectural-rule tags found in the
source. Every other command reads this model rather than re-reading your code.

Supported `--lang` values: `python`, `csharp`, `odin`, `lua`, `julia`, `typescript`, `svelte`.
Omit it and `cdec` detects the language from the file mix.

### 1.2 Get a human-editable version

XMI is verbose. The same model in **editor JSON** is far easier to read and edit:

```bash
cdec parse examples/python_demo --lang python --out demo.json
# or convert an existing model, in either direction:
cdec convert demo.xmi demo.json
```

The JSON is a snake_case mirror of the internal model:

```jsonc
{
  "source_language": "python",
  "packages": [
    {
      "name": "orders",
      "qualified_name": "orders",
      "classes": [
        {
          "name": "Receipt",
          "qualified_name": "orders.Receipt",
          "kind": "class",                  // class | abstract | interface | enum | struct
          "bases": [],
          "attributes": [
            { "name": "total", "type": "float", "visibility": "public" }
          ],
          "operations": [
            { "name": "formatted", "parameters": [], "return_type": "str",
              "visibility": "public" }
          ],
          "rules": [ { "id": "immutable" } ]
        }
      ]
    }
  ]
}
```

**Every command that reads or writes a model accepts either format**, chosen by file
extension. `parse --out m.json`, `render m.json`, `reference set m.json` and
`propose m.json` all work. You only need `convert` when you explicitly want the other
representation on disk.

### 1.3 Explore it in the browser

The fastest way to actually *look* at a codebase:

```bash
cdec serve parse examples/python_demo
```

This parses the tree and opens your browser straight to the class diagram at
`http://127.0.0.1:8765`. In the viewer you get:

- an interactive, draggable canvas (SvelteFlow + dagre auto-layout);
- a side panel with search, per-class visibility checkboxes, **Show all / Hide all**,
  **Isolate** (show a class and its N-hop neighbours), and **Compact**;
- a "Related" sub-list of inheritance and association neighbours;
- **saved views** you can export to `.cdecview.json` and share with teammates;
- diagram switching: **class**, **package**, **activity**, **sequence**.

To start the server without parsing anything (then register projects from the homepage):

```bash
cdec serve                       # http://127.0.0.1:8765
cdec serve --port 9000           # if 8765 is taken
```

### 1.4 Render a static diagram

For a one-shot image — a PR attachment, a wiki page, an architecture doc:

```bash
cdec render demo.xmi --diagram class   -o class.svg
cdec render demo.xmi --diagram package -o packages.svg
```

This path requires **Graphviz**. `--diagram` accepts `class`, `package`, `activity`, and
`sequence`; the latter two also need `--name`:

```bash
cdec render demo.xmi --diagram activity --name checkout -o checkout.svg
```

Activity and sequence diagrams only exist if the source contains **embedded diagram tags** —
see [Part 11](#115-embedded-diagram-tags).

### Try it

```bash
cdec serve parse examples/csharp_mvc_demo     # a small MVC codebase
cdec parse examples/typescript_demo --lang typescript --out ts.json
```

---

## Part 2 — See what changed

**Goal:** review architectural change, not line-by-line change. Still no configuration.

A normal `git diff` tells you *which lines* changed. These commands tell you *which classes,
methods, and dependencies* changed — and colour them: **green** added, **red** removed,
**yellow** changed.

### 2.1 Between two git revisions

```bash
cdec diff main feature-branch --lang python --out change.xmi
cdec render change.xmi --diagram class -o change.svg
```

Both revisions are checked out into a temporary directory, so **your working tree is never
touched**. Useful options:

| Option | Purpose |
|---|---|
| `--repo PATH` | Repository root, if not the current directory. |
| `--subpath DIR` | Only parse this directory of each revision — much faster on monorepos. |

```bash
# What did this PR do to the architecture?
cdec diff origin/main HEAD --lang python --subpath src --out pr.xmi
```

### 2.2 Against a stored snapshot

If you have checkpointed a model, compare live code against it:

```bash
cdec diff-vs-xmi baseline.xmi ./src --lang python --out drift.xmi
```

The XMI is the **old** side, the freshly-parsed source is the **new** side.

### 2.3 Between two existing models

When CI already produced a model for each branch, skip re-parsing:

```bash
cdec diff-xmi main.xmi pr.xmi --out delta.xmi
```

Both models must declare the same `source_language`.

### 2.4 Reviewing a diff in the browser

Load any annotated model in the viewer and the class diagram renders with diff styling plus
a **change walkthrough** — an ordered, class-by-class list of what changed, so a reviewer
can step through the architectural delta.

---

## Part 3 — Your first guardrail

**Goal:** make CI fail when someone breaks an architectural rule. This is where
configuration starts.

### 3.1 Initialise a project

```bash
cd /path/to/your/project
cdec init --lang python --source .
```

This scaffolds:

```
.cdec/
  rules.yaml       everything: settings, rules, exceptions, lock digests
  reference.xmi    a snapshot of the architecture as it is right now
  README.md        a short in-repo explainer
  .gitignore       ignores cache/
```

**Commit everything except `cache/`.** The `.cdec/` folder is the contract; it belongs in
version control so the whole team and CI share it.

`rules.yaml` has four parts, and you only write the first two:

```yaml
language: python          # what to check, and where
source: .
reference: .cdec/reference.xmi

rules: []                 # the laws you opt into — you write these

# >>> cdec: managed section — written by the tool, below the marker
exceptions: [...]         # violations you accepted, each with its reason
locks: [...]              # approved digests of frozen implementations
```

The tool rewrites only what is below the marker, so every comment and `message:` block
you write above it survives untouched.

**Where `reference.xmi` comes from.** It is a parsed snapshot of your architecture, and
`cdec init` takes the first one for you. Two rules need it: any `scope: diff` rule uses it
as the "before" side, and the `reference-architecture` rule of [Part 7](#part-7--the-reference-gate)
gates against it directly. Re-take it whenever a change to the architecture is deliberate
and approved:

```bash
cdec check --automatic-exceptions reference    # snapshot what the code IS
cdec reference set target.json                 # declare what it SHOULD BECOME
```

The distinction matters and comes back in [Part 8](#part-8--designing-before-you-build).

> **Upgrading a project that predates this layout?** Older versions split the same content
> across `config.yaml`, `baseline.yaml` and `locks.yaml`. Those are still read, and
> `cdec init --migrate` folds them into `rules.yaml` and deletes them.

`cdec init` scaffolds `.cdec/` only. To also install the language **rule shim** and the
bundled Claude assets, run:

```bash
cdec update-assets
```

```
updated .claude/agents/cdec-architect.md
updated .claude/agents/oop-refactor-architect.md
updated .claude/skills/cdec-architecture-loop/SKILL.md
updated cdec_rules.py
```

You need the shim (`cdec_rules.py` for Python, `CodeConstraintsRules.cs` for C#) before
[Part 5](#part-5--tagging-code-with-constraints). The interactive session — `cdec` with no
subcommand — walks you through both steps with prompts.

### 3.2 Run the drift check

```bash
cdec check
```

```
cdec check: no violations.
```

Right now it passes no matter what you do, because `rules.yaml` starts with `rules: []`.
`cdec check` is **opt-in**: it only enforces what you explicitly ask for. That is the point —
you add laws one at a time as the team agrees on them.

### 3.3 Add a real rule

Say your `catalog` package holds pure domain data and must not depend on workflow packages.
Add this to `.cdec/rules.yaml`:

```yaml
rules:
  - id: catalog-is-a-leaf-package
    type: forbidden-package-references
    severity: error
    from: ["catalog"]
    to: ["orders", "users", "notifications"]
    message: |
      Layering violation: '{source}' must not depend on '{target}'.
      `catalog` must stay at the bottom of the dependency graph so any
      caller can use it without dragging in workflow packages.
```

Now `cdec check` fails — with your explanation, not a generic error — if anyone imports
`orders` from `catalog`.

The `message` field supports `{placeholders}` drawn from the violation (`{qualified_name}`,
`{source}`, `{target}`, `{member}`, `{action}`, …). **Use it.** A rule that explains *why*
teaches; a rule that just says "violation" breeds resentment.

### 3.4 Adopting on an existing codebase

Real codebases already violate the rules you want. Three escape hatches, in order of
preference:

**1. Baseline the existing violations** — turn on the rule, grandfather today's failures,
and prevent *new* ones:

```bash
cdec check --automatic-exceptions rules
```

This records current violations into the `exceptions:` section of `.cdec/rules.yaml`. They are reported as
*suppressed* instead of failing. Any **new** violation of the same rule still fails. This is
the ratchet: the codebase can only get better.

**2. Accept them one at a time, with reasons** — see [§3.7](#37-accepting-a-violation--the-review-loop).
Slower than `--automatic-exceptions rules`, and much better on a codebase you intend to keep: each
waiver carries the reason it was granted.

**3. Downgrade the severity** — `severity: warning` reports without failing. Combine with
`--fail-on warning` later to tighten the screw.

```yaml
  - id: bounded-class-fanout
    type: max-class-fanout
    severity: warning
    limit: 6
```

### 3.5 Comparing against a branch instead of a snapshot

Rules with `scope: diff` need a baseline. By default that is `.cdec/reference.xmi`. In a PR
pipeline it is usually better to diff against the target branch live:

```bash
cdec check --base-ref origin/main
```

Baseline resolution order: `--base-ref` → `--reference` → the `reference:` setting in
`rules.yaml` → `.cdec/reference.xmi`. With no baseline at all, `scope: diff` rules are
**skipped** rather than silently passing — the report lists them under "skipped".

### 3.6 Accepting an intentional architectural change

When a change is deliberate, a reviewer approves it and the author re-snapshots:

```bash
cdec check --automatic-exceptions reference     # rewrites .cdec/reference.xmi
git add .cdec/reference.xmi
```

Committing the regenerated snapshot **in the same PR** is what makes the change reviewable:
the model delta shows up in the diff.

### 3.7 Accepting a violation — the review loop

Re-snapshotting the reference (§3.6) accepts *everything*. Usually you want the opposite:
this one violation is fine, the rest still block. That is `cdec exceptions`.

Every issue the tool reports leads with a **key**:

```
[no-new-classes] (error)
  - [V-DD3EA5B2] animals.Cat — animals/cat.py:1: New class 'animals.Cat' was added.
```

The prefix names which kind of rule reported it:

| Prefix | Reported by |
|---|---|
| `V-` | a configured architectural rule (Part 4) |
| `F-` | `tag-conformance` (Part 5) |
| `L-` | `implementation-locks` (Part 6) |
| `R-` | `reference-architecture` (Part 7) |

The key hashes *what* the issue is — rule kind, element, discriminator — and never where
it sits, nor which `rules.yaml` entry surfaced it, so:

- re-running over unchanged code always gives the same key,
- reformatting the file or moving the class does not invalidate an exception you granted, and
- renaming the `rules.yaml` entry does not either.

**Accept one by key:**

```bash
cdec exceptions allow V-DD3EA5B2 --reason "agreed in ARCH-42"
cdec check      # now passes
```

**Or review a batch in a text editor.** Save the report, mark the lines you accept, apply
the file:

```bash
cdec exceptions review --out review.txt
```

```
- [V-DD3EA5B2] [error] [no-new-classes] [animals/cat.py:1] animals.Cat: New class 'animals.Cat' was added.
- [V-9B4C7A21] [error] [no-new-classes] [animals/lion.py:1] animals.Lion: New class 'animals.Lion' was added.
```

Add `[ALLOW]` — anywhere on the line — to the ones you accept, with an optional reason:

```
- [ALLOW: intentional, ARCH-42] [V-DD3EA5B2] [error] [no-new-classes] [animals/cat.py:1] animals.Cat: …
- [V-9B4C7A21] [error] [no-new-classes] [animals/lion.py:1] animals.Lion: …
```

```bash
cdec exceptions patch --file review.txt
cdec check      # Cat is accepted; Lion still fails
```

The parser only needs a marker and a key on the same line, so **`cdec check --log-out
check.log` output is patchable as-is** — the `review` command is a convenience, not a
required format. A `#` at the start of a line comments it out, which is how you cancel a
decision without deleting the evidence. `--file -` reads from stdin.

**Managing what you've accepted:**

```bash
cdec exceptions list                 # what's allowed, why, when, and by whom
cdec exceptions remove V-DD3EA5B2    # withdraw — the issue blocks again
cdec exceptions prune                # drop waivers whose issue no longer occurs
```

Run `prune` periodically. A waiver outlives the code it was granted for, and a stale one
silently pre-approves the *next* violation of that rule on that element.

Two things this deliberately will not do:

- **A key that matches no current issue is an error**, not a silent no-op — it nearly
  always means the report you are quoting is out of date.
- **Lock violations (`L-`) cannot be waived here.** `cdec exceptions allow` on one prints the
  privileged command instead (`cdec check --automatic-exceptions locks --target … --force`). See
  [§6.4](#64-the-privilege-boundary--the-part-that-matters) for why that boundary exists.

Because keys are stable and every command speaks `--format json`, this loop scripts
cleanly: an agent can run `cdec check --format json`, decide, and call
`cdec exceptions allow <key> --reason "…"` without parsing prose.

### Try it against the demo

```bash
cdec check --config examples/python_demo/.cdec --source examples/python_demo
```

The demo ships a fully-populated `rules.yaml` — twelve rules covering structural drift,
package layering, naming, cycles, and fanout, each with a written explanation. It is the
best available template for your own.

---

## Part 4 — The rule catalogue

**Goal:** know what you can enforce. These are the `type:` values for `rules.yaml`.

> This part is the overview. For each rule's full option list, a sample configuration, and a
> worked passing/failing pair, see the
> **[Rules & constraints catalogue](RULES_CATALOGUE.md#1--configured-rules-cdecrulesyaml)**.

Every rule accepts the common fields `id` (unique, stable — it is the key in
the `exceptions:` list), `type`, `severity` (`error` | `warning` | `off`), `scope`
(`diff` | `snapshot`), `message`, and `ignore` (a list of qualified-name globs, where `**`
matches across dots).

### 4.1 Structural drift (default `scope: diff` — needs a baseline)

| `type` | Options | Fires when |
|---|---|---|
| `no-new-classes` | `ignore` | A class is added vs the baseline. |
| `no-removed-classes` | `ignore` | A class is removed vs the baseline. |
| `frozen-members` | `classes`, `members`, `kinds` | An attribute/operation on a matched class is added, removed, or changed. |
| `frozen-rules` | `classes` | An architectural-rule tag present in the baseline is removed or weakened. |

`frozen-members` is how you protect a public contract:

```yaml
  - id: lock-notification-abc
    type: frozen-members
    severity: error
    classes: ["notifications.Notification"]
    kinds: [operation]
    message: |
      The {kind} '{member}' on '{qualified_name}' was {action}.
      Notification is a public contract — every concrete notifier must
      keep its signature stable.
```

`frozen-rules` protects the *tags* themselves, so nobody can quietly delete an
`@immutable` to make their change compile.

### 4.2 Dependency rules

| `type` | Options | Fires when |
|---|---|---|
| `forbidden-references` | `from`, `to` | A class in `from` references a class in `to`. |
| `forbidden-package-references` | `from`, `to` | A package in `from` references a package in `to`. |
| `no-cyclic-package-dependencies` | — | A dependency cycle exists between packages. |
| `layer-dependencies` | `allow` | A class references a class in a layer the `allow` matrix forbids. |

`layer-dependencies` reads `@layer("name")` tags from the source and enforces a direction
matrix — the cleanest way to express a layered architecture:

```yaml
  - id: layering
    type: layer-dependencies
    severity: error
    allow:
      presentation: [application, domain]
      application:  [domain]
      domain:       []            # domain depends on nothing
      infrastructure: [domain]
```

Anything not listed is forbidden. Here, `domain` referencing `infrastructure` fails — the
classic dependency-inversion rule, enforced.

### 4.3 Shape rules (default `scope: snapshot`)

| `type` | Options | Fires when |
|---|---|---|
| `dangling-classes` | `entry_points`, `framework_bases` | No other class in the project references it. |
| `subclass-naming` | `base`, `name_pattern` | A subclass of `base` has a name not matching the pattern. |
| `max-class-fanout` | `limit` (default `10`) | A class references more than `limit` others. |

```yaml
  - id: notifiers-must-be-named-Notifier
    type: subclass-naming
    severity: error
    base: "Notification"
    name_pattern: ".*Notifier$"
```

`dangling-classes` needs help distinguishing dead code from framework-wired entry points —
list those under `entry_points` (qualified-name globs) or `framework_bases`.

### 4.4 Reports for humans and machines

```bash
cdec check --format json --json-out lint.json    # machine-readable artefact
cdec check --log-out check.log                   # tee the human report
cdec check --fail-on warning                     # tighten the gate
cdec check --fail-on none                        # report only, never fail
```

---

## Part 5 — Tagging code with constraints

**Goal:** attach a design constraint to a class or method and have the tool verify the
*implementation* honours it.

The rules in Part 4 look only at the model — names, types, references. This one goes
further: it re-parses the source and **inspects method bodies**. Turn it on by adding one
entry to `.cdec/rules.yaml`:

```yaml
  - id: tags-must-be-honoured
    type: tag-conformance
    severity: error
```

There is no second command. `cdec check` runs it with everything else.

### 5.1 The shims

Tags are ordinary Python decorators / C# attributes that do nothing at runtime. They ship as
no-op shims so tagged code still imports and compiles:

```bash
# dropped into your project root by `cdec init`, or refreshed later with:
cdec update-assets
```

- Python → `cdec_rules.py`, imported as `from cdec_rules import …`
- C# → `CodeConstraintsRules.cs`, namespace `CodeConstraints.Rules`

**A tag is only recognised when imported from the shim namespace.** Your own decorator
called `sealed` will never be mistaken for the architectural one.

### 5.2 The catalogue

> Each tag's parameters, detection semantics, and a passing/failing pair are in the
> **[Rules & constraints catalogue](RULES_CATALOGUE.md#2--source-level-constraint-tags)**.

| Tag | Python / C# | Applies to | Enforced by | Meaning |
|---|---|---|---|---|
| `no-instantiation` | `@no_instantiation` / `[NoInstantiation]` | class, method | `enforce` (body) | May not construct objects, except types in `allow`. |
| `factory` | `@factory(creates=[…])` / `[Factory]` | class, method | `enforce` (body) | The only place allowed to construct those types. |
| `immutable` | `@immutable` / `[Immutable]` | class | `enforce` (body) | Fields may not be reassigned after construction. |
| `sealed` | `@sealed` / `[Sealed]` | class | `enforce` (structural) | May not be subclassed. |
| `layer` | `@layer("name")` / `[Layer("name")]` | class | `check` | Assigns an architectural layer. |
| `locked` | `@locked` / `[Locked]` | class, method, function | `lock check` | Implementation frozen — see [Part 6](#part-6--freezing-implementations). |
| `no-side-effects` | `@no_side_effects` / `[NoSideEffects]` | method | *drift only* | Declares purity. **Body analysis is not implemented** — the tag is captured, shown, and drift-frozen, but not verified. |

### 5.3 A worked example

```python
from cdec_rules import factory, immutable, layer, locked, no_instantiation, sealed


@immutable
@sealed
@layer("orders")
class Receipt:
    """Built once, never mutated, never subclassed."""

    def __init__(self, total: float, lines: int) -> None:
        self.total = total
        self.lines = lines


@layer("orders")
class ReceiptFactory:
    @factory(creates=["Receipt"])
    def build(self, cart: Cart) -> Receipt:
        return Receipt(cart.total(), len(cart.items))     # allowed: this IS the factory


@layer("orders")
class CheckoutService:
    @no_instantiation
    def quick_receipt(self, cart: Cart) -> Receipt:
        return Receipt(cart.total(), 1)                   # VIOLATION x2
```

```bash
cdec check --config examples/python_demo/.cdec --source examples/python_demo
```

```
[tags-must-be-honoured] (error)
  - [F-5BBDCC93] orders.CheckoutService — orders/billing.py:97: [no-instantiation]
      'orders.CheckoutService.quick_receipt' is tagged @no_instantiation but
      constructs 'Receipt'.
  - [F-4E5B2B91] orders.CheckoutService — orders/billing.py:97: [factory]
      'orders.CheckoutService.quick_receipt' constructs 'Receipt' outside its
      designated factory (ReceiptFactory).

Summary: 2 error(s), 0 warning(s).
```

Two tags, two independent findings, exit code `1`. The bundled demos ship this exact seeded
violation so you can see a real failure — route the call through the factory and the run
goes green.

Note the `F-` keys. They identify the *finding*, not the `rules.yaml` entry, so renaming
`tags-must-be-honoured` never invalidates an exception granted against it.

### 5.4 Escape hatches and precision

`@no_instantiation` accepts an `allow` list for types that are fine to construct:

```python
@no_instantiation(allow=["list", "dict", "Decimal"])
def summarise(self): ...
```

You will need it in Python, because **detection is heuristic there**: with no type
resolution available, a "construction" is a call whose callee is a known project class *or*
is Capitalised. In C# detection is precise — it keys off `object_creation_expression` nodes,
so `new Foo()` is unambiguous.

### 5.5 Adopting one tag at a time

On a mature codebase, turning every tag on at once produces a wall of red. The `rules:`
option narrows what is checked, so you can adopt them in the order the team agrees on:

```yaml
  - id: tags-must-be-honoured
    type: tag-conformance
    severity: error
    rules: [sealed, immutable]     # factory and no-instantiation come later
```

`ignore:` takes qualified-name globs, the same as every other rule, and findings you accept
through [`cdec exceptions`](#37-accepting-a-violation--the-review-loop) are silenced like
any other violation.

Under the hood this stays a separate engine: it never consults the reference model or the
diff, so its findings are always about the code as it stands right now.

---

## Part 6 — Freezing implementations

**Goal:** declare that a specific function body is settled and must not change. Python, C#,
Odin, Lua and Julia — every language with an AST fingerprinter. TypeScript and Svelte are
refused by name.

Parts 4 and 5 ask "did the design drift?" and "does the code obey its tags?". This asks
something narrower and stricter: **did this body change at all?**

Use it for the code where correctness was hard-won: a settlement calculation finance signed
off on, a security check, a tax rule, a serialisation format other systems depend on.

### 6.1 The key property: locks are AST identities, not line ranges

Moving a locked function down the file, reformatting it, renaming a local variable, or
editing a comment **does not** trip the lock. Any semantic change does. This is what makes
locks livable — they do not fight your formatter or your refactors.

### 6.2 Locking something

Turn the rule on, tag the code, then record the digest:

```yaml
# .cdec/rules.yaml
  - id: frozen-implementations
    type: implementation-locks
    severity: error
```

```python
from cdec_rules import locked

class Receipt:
    @locked(reason="receipt wording is contractual; finance signed off on it")
    def formatted(self) -> str:
        return f"{self.lines} line(s) — total {self.total:.2f}"
```

```bash
cdec check --automatic-exceptions locks
```

```
[frozen-implementations] recording the current state:
  + locked   orders.Receipt.formatted  (method, def9d237e48b)
  wrote 1 lock(s) to .cdec
```

The approved digest lands in the `locks:` section of the same `rules.yaml`:

```yaml
locks:
- target: orders.Receipt.formatted
  kind: method
  algo: py-ast/1
  digest: def9d237e48b6d2aae2cc46251c3b670d563130c551bf3116d394a097fe35863
  file: orders/billing.py
  locked_at: '2026-08-02T21:00:38+00:00'
  locked_by: Fran
  reason: receipt wording is contractual; finance signed off on it
```

Commit it. From here `cdec check` verifies the lock on every run, and
`cdec locks` shows what is frozen (`--all` also lists everything that *could* be).

### 6.3 What the rule catches

| Kind | Headline | Meaning |
|---|---|---|
| `changed` | frozen implementation changed | The body's digest no longer matches. |
| `missing` | declared `@locked` but not baselined | Tagged but never recorded, so nothing is verified. |
| `removed` | frozen element no longer exists | The locked element was deleted or renamed. |
| `unlocked` | `@locked` tag was removed | Someone deleted the tag but left the ledger entry. |
| `algo-mismatch` | digest algorithm changed | The ledger predates a fingerprinter change — re-baseline. |

Note `unlocked`: **you cannot escape a lock by deleting the tag.** The ledger is the
authority, and removing the tag is itself the violation.

### 6.4 The privilege boundary — the part that matters

`--automatic-exceptions locks` is deliberately split into a safe operation and a privileged
one:

```bash
# SAFE. Only ADDS locks for newly tagged code. Anyone can run it, because it
# can never erase the evidence that frozen code changed.
cdec check --automatic-exceptions locks

# PRIVILEGED. Accepts a change to frozen code, and prunes released entries.
cdec check --automatic-exceptions locks --force
```

Only `--force` re-baselines a drifted digest — and it produces a **reviewable diff on the
`locks:` section of `.cdec/rules.yaml`**. Put that file behind a CODEOWNERS entry and
re-baselining becomes a lead-only action that always leaves a trail:

```
# CODEOWNERS
/.cdec/rules.yaml    @your-org/tech-leads
```

That is the whole design: a junior developer or an agent *can* change locked code, but they
cannot make CI green without a lead approving a visible ledger change.

The same boundary holds from the other direction. A lock violation carries an `L-` key like
any other issue, but `cdec exceptions allow` **refuses** it and prints the command above
instead — and `--automatic-exceptions rules` will not grandfather one either. There is
exactly one way to accept a change to frozen code, and it leaves a diff.

### 6.5 Emergency bypass

```bash
cdec check --bypass-locks --bypass-reason "hotfix INC-4412, follow-up ticket ARCH-88"
```

Bypass still collects violations, prints an audit banner, and sets `summary.bypassed` in the
JSON report — so your pipeline can **reject bypassed runs** on protected branches rather
than silently accepting them. `CDEC_LOCK_BYPASS=1` is the environment-variable equivalent.

### 6.6 Locking without decorating

To freeze code you would rather not annotate (or cannot), give the rule globs:

```yaml
  - id: frozen-implementations
    type: implementation-locks
    severity: error
    include_docstrings: false     # do docstring edits count as implementation changes?
    targets:
      - "orders.pricing.**"       # freeze an entire module subtree
```

### 6.7 Two details worth knowing

- **Same-named siblings are grouped.** Overloads, and `@property` + its setter, become one
  target. Adding an overload to a locked name is therefore itself a violation.
- **Docstrings are stripped by default**, so improving documentation never trips a lock.
  Set `include_docstrings: true` if the text is contractual.

### 6.8 Turning it off

The rule is opt-in like every other: delete the entry, or set `severity: off`. A project
with no `implementation-locks` rule never sees lock output, even if the code carries
`@locked` tags — `cdec check` enforces what the file asks for and nothing more.

---

## Part 7 — The reference gate

**Goal:** freeze the entire public shape of a codebase, with no per-rule configuration.

The rules in Part 4 are scalpels — each enforces exactly the law you wrote down. This one
is a wall: **any** structural deviation from the committed snapshot fails.

```yaml
# .cdec/rules.yaml
  - id: public-shape-is-frozen
    type: reference-architecture
    severity: error
```

```bash
cdec check
```

```
[public-shape-is-frozen] (error)
  - [R-7C41B0AE] catalog.Author — Property 'test_var:float' was added to 'catalog.Author'.

Summary: 1 error(s), 0 warning(s).
```

It compares against the `reference:` model from Part 3 by default; `reference:` on the rule
itself overrides that per rule.

### 7.1 What it catches that the other rules do not

This is the subtle and important part. The two mechanisms sit on **different comparison
engines**:

- `frozen-members` and the other `scope: diff` rules read the diff engine, which matches
  members by **signature** and only marks a matched member changed when its *rule tags*
  differ. It is therefore **blind** to access-level changes (`public` → `private`),
  modifier changes (`static`, `abstract`, `readonly`), and class-kind changes.
- `reference-architecture` runs a dedicated comparator that walks both models field by
  field and **does** catch all of those.

So a pull request that flips a public method to private, or makes a concrete class
abstract, **passes `frozen-members`** and **fails `reference-architecture`**. That gap is
the entire reason the gate exists as a rule of its own rather than an option on another.

To narrow it, name the deviation categories you care about:

```yaml
  - id: nothing-is-removed
    type: reference-architecture
    severity: error
    categories: [class-removed, operation-removed, attribute-removed]
```

### 7.2 The workflow

```
gate fails  →  reviewer agrees the change is intended
            →  author runs `cdec check --automatic-exceptions reference`
            →  commits the new reference.xmi in the same PR
            →  gate passes
```

Committing the regenerated snapshot **in the same pull request** is what makes the change
reviewable: the model delta shows up in the diff, next to the code that caused it.

An `R-` deviation is an ordinary issue in every other respect — unlike a lock, you can
accept a single one with `cdec exceptions allow R-XXXXXXXX --reason "..."` when
re-snapshotting the whole model would say more than you mean.

`cdec reference show` opens the viewer on code-versus-reference.

### 7.3 A directional gotcha

`cdec reference show` treats the reference as the **target** architecture and your code as
the current state — so things present in the reference but missing from the code appear as
**green additions** ("still to build"). That is deliberately the inverse of the
`reference-architecture` rule and of `diff-vs-xmi`, where the reference is the *old* side.

### 7.4 Choosing your gate

Four questions, four rule types — and one command that runs whichever of them you switched
on:

| You want to say | Add this rule |
|---|---|
| "These specific architectural laws are never broken" | any rule from [Part 4](#part-4--the-rule-catalogue) |
| "Tagged code must actually honour its constraint" | `tag-conformance` |
| "*This function* is settled — nobody touches it" | `implementation-locks` |
| "Nothing about the public shape changes without review" | `reference-architecture` |

```bash
cdec check      # runs every one of them you configured
```

They compose. Many teams run the reference gate as a hard backstop *and* the specific rules
that carry semantic meaning, in the same file.

---

## Part 8 — Designing before you build

**Goal:** agree on a target architecture *first*, then constrain development toward it. This
inverts everything so far: instead of describing what the code is, you describe what it
should become.

### 8.1 The loop

```
author a model  →  cdec propose  →  look & discuss  →  edit  →  propose again
                                                              ↓
                                                    cdec reference set
                                                              ↓
                                       cdec check now constrains development
                                       toward the agreed target
```

### 8.2 Start from reality

Rather than writing a model from scratch, export what exists and edit it:

```bash
cdec parse ./src --lang python --out target.json
```

Now edit `target.json` — add the classes you intend to build, delete what should go, add
`rules` entries to encode constraints. It is plain JSON; a person or an AI agent can edit it.

### 8.3 Show the proposal as a diff

```bash
cdec propose target.json --source ./src --lang python --focus Billing,Invoice
```

The browser opens on your proposal **diffed against the current code**:

- **green** = in the target but not yet in the code → still to build
- **red** = in the code but not in the target → to be removed
- **yellow** = present in both but changed

`--focus` pre-filters the canvas to the classes under discussion, which matters on a large
codebase.

**Re-running `cdec propose` refreshes the already-open tab in place** — no new tabs, no
manual reload. That is what makes it a conversation: edit the model, re-propose, discuss,
repeat. Positions and visibility survive the refresh.

```bash
cdec propose target.json --against reference    # diff vs the current reference instead
cdec propose target.json --no-browser           # just push and print the URL
```

### 8.4 Lock in the agreement

```bash
cdec reference set target.json
```

This promotes your authored model to `.cdec/reference.xmi`. Note the distinction:

| Command | Meaning |
|---|---|
| `cdec check --automatic-exceptions reference` | "Snapshot **what the code is**." (accept a change) |
| `cdec reference set MODEL` | "Declare **what the code should become**." (accept a design) |

From here on `cdec check` measures the code against the agreed target — every
`scope: diff` rule uses it as the baseline, and a `reference-architecture` rule gates on it
directly. Because the target contains classes that do not exist yet, `cdec reference show`
renders them green: a live build-out checklist.

### 8.5 Editing in the browser instead

The viewer has a full editor mode: double-click a class to edit it, hover for quick
"+ attribute" / "+ method", press Delete to remove. A two-way JSON panel sits beside the
canvas, so you can type JSON or drag boxes and the other side follows. Load a baseline and
turn on **Compare** to get live diff styling as you edit.

---

## Part 9 — Wiring up CI/CD

**Goal:** make the guardrails automatic. There is one command and one exit code, so this
works in any CI system without parsing output.

### 9.1 The whole pipeline step

```bash
cdec check
```

Two files are committed and two files are all CI needs: `.cdec/rules.yaml` and
`.cdec/reference.xmi`. Everything you switched on in Parts 4 to 7 runs in that one
invocation.

`cdec` can also emit ready-made wrappers — `cdec-ci.sh` and `cdec-ci.bat` — from the
interactive session (`cdec` with no subcommand → "Generate CI/CD scripts").

### 9.2 GitHub Actions

```yaml
name: architecture
on: [pull_request]

jobs:
  constraints:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0            # `--base-ref` needs history

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - run: pip install code-constraints

      - name: Architectural constraints
        run: cdec check --base-ref origin/${{ github.base_ref }} --json-out report.json

      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: constraint-report
          path: report.json
```

`fetch-depth: 0` matters — `--base-ref` parses the target branch live, which needs history.

### 9.3 GitLab CI

```yaml
architecture:
  image: python:3.12
  script:
    - pip install code-constraints
    - cdec check --base-ref origin/$CI_MERGE_REQUEST_TARGET_BRANCH_NAME --json-out report.json
  artifacts:
    when: always
    paths: [report.json]
```

### 9.4 Pre-commit

Catch violations before they reach CI:

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: cdec-check
        name: cdec check
        entry: cdec check
        language: system
        pass_filenames: false
```

### 9.5 Rejecting bypassed runs

If you allow `--bypass-locks`, make sure it cannot pass silently on a protected branch:

```bash
cdec check --json-out report.json
python -c "
import json, sys
if json.load(open('report.json'))['summary'].get('bypassed'):
    sys.exit('locks were bypassed — not allowed on this branch')
"
```

`summary.skipped` is worth watching too: a rule that could not run reports as skipped rather
than passing, and a gate that quietly stopped guarding is the failure mode to catch early.

### 9.6 A sane adoption sequence

Turning everything on at once on a mature codebase produces a wall of red and a team that
disables the tool. Instead, add one rule type per week:

1. **Week 1 — observe.** `cdec check --fail-on none`. Nothing fails; you collect data.
2. **Week 2 — ratchet.** Add dependency and layering rules, run
   `cdec check --automatic-exceptions rules`, commit `rules.yaml`. Existing problems are
   grandfathered; new ones fail.
3. **Week 3 — tag the crown jewels.** Add `@sealed` / `@immutable` / `@factory` to the
   classes where the design genuinely matters, and add a `tag-conformance` rule.
4. **Week 4 — lock the untouchables.** `@locked` on the handful of bodies that must not
   change, an `implementation-locks` rule, and `.cdec/rules.yaml` behind CODEOWNERS.
5. **Later — consider `reference-architecture`**, once the architecture is stable enough
   that every structural change *should* be deliberate.

Then work the exceptions down over time. A shrinking `exceptions:` list is a good team
metric, and `cdec exceptions prune` keeps it honest by dropping the entries whose issue no
longer occurs.

---

## Part 10 — Constraining AI agents and new contributors

**Goal:** the use case the tool is built for — keeping junior developers, external
contributors, and coding agents inside the boundaries the team agreed on.

### 10.1 Why this works on agents

An AI agent will happily write code that compiles, passes tests, and quietly violates a
design decision made two years ago in a meeting it was not in. Constraints move that
decision out of tribal memory and into a file that fails the build.

The guardrails compose into a layered net:

| Layer | Stops | Rule type |
|---|---|---|
| Target architecture | Building the wrong thing | `reference-architecture` |
| Dependency & layering rules | Wiring it up wrongly | `forbidden-*-references`, `layer-dependencies` |
| Constraint tags | Ignoring a design constraint | `tag-conformance` |
| Locks | Touching settled code | `implementation-locks` |

All four live in `.cdec/rules.yaml` and all four run in `cdec check`, which matters more for
an agent than for a person: one command to put in its build loop, one report to read, and
no way to satisfy the gate by running only three quarters of it.

### 10.2 Bundled Claude assets

`cdec update-assets` (or the interactive `cdec` session) drops these into the project:

| Asset | Purpose |
|---|---|
| `cdec-architect` (agent) | Translates specs into class diagrams, proposes patterns, defines constraints, drives the propose → review → lock loop. |
| `oop-refactor-architect` (agent) | Analyses an existing class structure and proposes refactors, layering, and rules — good for onboarding a mature codebase. |
| `cdec-architecture-loop` (skill) | Teaches any Claude session the propose → review → lock workflow. |

### 10.3 A practical agent workflow

```bash
# 1. Agree the design with the agent, visually, before any code is written.
cdec parse ./src --lang python --out target.json
#    (agent edits target.json)
cdec propose target.json --focus PaymentGateway,Invoice
#    ... discuss, agent edits, re-propose, repeat ...

# 2. Freeze the agreement.
cdec reference set target.json

# 3. Let the agent implement. Its own feedback loop now includes the constraints:
cdec check

# 4. CI enforces the same thing on the PR.
```

Point the agent at `cdec check` as part of its build loop and it will self-correct against
your architecture instead of yours-in-theory. When it hits a violation it believes is
correct, the honest move is `cdec exceptions allow <key> --reason "..."` — which records
the decision where you will see it in review, rather than editing the rule away.

The one thing it cannot do is accept a lock. `cdec exceptions allow` refuses an `L-` key, so
changing frozen code always needs a human running
`cdec check --automatic-exceptions locks --force`.

### 10.4 Make the messages teach

The `message:` field is the highest-leverage thing in `rules.yaml`. Compare:

> `forbidden-package-references: catalog -> orders`

with:

> `Layering violation: 'catalog' must not depend on 'orders'. catalog describes books and
> authors — pure domain data. It must stay at the bottom of the dependency graph so any
> caller can use it without dragging in orders/users/notifications. Move the offending
> reference to whichever package owns the workflow (likely orders).`

The second turns a failed build into onboarding — for a person or an agent. The bundled
demo's `rules.yaml` is written this way throughout; copy its style.

---

## Part 11 — Language specifics

> **Each language has a full guide of its own.** This part is the summary; the
> **[per-language guides](languages/README.md)** walk the entire workflow in each language's
> own idiom, with its parser gotchas and a runnable demo:
> **[Python](languages/PYTHON.md)** · **[C#](languages/CSHARP.md)** ·
> **[Odin](languages/ODIN.md)** · **[Lua](languages/LUA.md)** ·
> **[Julia](languages/JULIA.md)** · **[TypeScript & Svelte](languages/TYPESCRIPT-SVELTE.md)**

### 11.1 Capability matrix

Support is **layered**, and the layers are independent. A language always has a parser;
tags, `tag-conformance` and `implementation-locks` each need extra machinery on top.

| Capability | Python | C# | Odin | Lua | Julia | TypeScript | Svelte |
|---|---|---|---|---|---|---|---|
| Parse to model | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Diagrams, diff, model rules | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `reference-architecture` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Constraint tags | ✅ decorators | ✅ attributes | ✅ `//@cdec` | ✅ `---@cdec` | ✅ macros | ❌ | ❌ |
| `tag-conformance` | ✅ heuristic | ✅ precise | ✅ precise | ✅ idiom-based | ✅ name-based | ❌ | ❌ |
| `implementation-locks` | ✅ `py-ast/1` | ✅ `cs-ts/1` | ✅ `odin-ts/1` | ✅ `lua-ts/1` | ✅ `jl-ts/1` | ❌ | ❌ |
| Activity / sequence tags | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |

TypeScript and Svelte are fully supported for **modelling, the model rules and the
reference gate** — parsing, diagrams, diffing, dependency and layering rules. They have no
constraint tags yet, so `tag-conformance` and `implementation-locks` refuse them **by
name**: `cdec check` reports the rule as *skipped* with the reason, rather than reporting
"clean" while checking nothing.

### 11.2 The three tag syntaxes

The same seven tags, spelled in each language's own idiom — one catalogue entry defines all
of them, so the vocabulary can't drift:

```python
@sealed                              # Python — decorator, gated by `from cdec_rules import …`
@layer("orders")
class Receipt: ...
```

```csharp
[Sealed]                             // C# — attribute, gated by `using CodeConstraints.Rules;`
[Layer("orders")]
public class Receipt { }
```

```julia
@sealed @layer "orders" struct Receipt   # Julia — macros, gated by `using CdecRules`
    total::Float64
end
```

```lua
---@cdec sealed                      -- Lua — annotation comment
---@cdec layer("orders")
local Receipt = {}
```

```odin
//@cdec sealed                       // Odin — annotation comment
//@cdec layer("orders")
Receipt :: struct { total: f64 }
```

**Why Lua and Odin differ.** Python, C# and Julia each have a construct that can be defined
as a no-op — a decorator, an attribute, a macro — so the tag is a shipped shim you import,
and importing it is also the gate. Lua has no declaration modifiers at all, and the Odin
compiler *rejects unknown `@(...)` attributes*, so a no-op `@(cdec_sealed)` would not build.
Both therefore carry the tag in a namespaced comment where a decorator would go, and the
`@cdec` prefix plays the gating role the import plays elsewhere.

⚠️ **Julia's arguments are space-separated**: `@layer "orders"` is correct;
`@layer("orders")` is a Julia syntax error.

⚠️ **Lua and Odin tags need line adjacency** — a blank line between the comment and the
declaration detaches the tag.

### 11.3 Languages without classes

Odin, Lua and Julia have no `class`, so an operation's owner is derived:

- **Odin and Julia** — the type of the function's **first parameter**, so
  `proc(r: ^Receipt)` / `formatted(r::Receipt)` becomes a method on `Receipt`. This is what
  makes a tag on a package-scope procedure constrain the method a reader expects.
- **Lua** — the table the function is written on (`function Receipt:formatted()`).
- **Receiver-less callables** land on a synthetic `static` class named after the file stem,
  so a tag on a free function is never silently dropped.

See the per-language guides for the full mapping, including Odin's `using` embedding as
inheritance and Lua's table-promotion rule.

### 11.4 Per-language notes

**Python** — stdlib `ast`. Instance attributes come from `self.x = …` in `__init__`. Engine
B is **heuristic** (no type resolution: a "construction" is a call whose callee is a project
class or is Capitalised) — use `allow=[…]` to suppress false positives.

**C#** — `tree-sitter-c-sharp`; classic and file-scoped namespaces both work. Engine B is
**precise** (`object_creation_expression`).

**Odin** — `tree-sitter-odin`. Engine B is **precise**: composite literals (`Money{…}`) plus
`new`/`make`. `using base: Invoice` maps to inheritance.

**Lua** — `tree-sitter-lua`. A table is promoted to a class only when it has a method, an
`__index`, a metatable base, or a tag. Engine B is **idiom-based**: `T.new(…)` and
`setmetatable(t, T)`; a bare `T(…)` is `__call`, not a constructor.

**Julia** — `tree-sitter-julia`. Engine B is **name-based**: a call counts only when its
callee is a type this parse saw. Multiple dispatch means every method of one name groups
into a single lock target.

**TypeScript & Svelte** — `type_alias_declaration` maps to `interface`. The Svelte parser
handles `.svelte` + `.ts` together and resolves component imports into relationships.

⚠️ **Tree-sitter provides no semantic resolution** in any of these. A reference through an
import alias renders as the alias — keep that in mind when writing `forbidden-references`
patterns.

### 11.5 Embedded diagram tags

Python and C# support XML-style comment tags marking regions for **activity** and
**sequence** diagrams:

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

Supported: `<uml-class />`, `<uml-activity name="…" granularity="control-flow|statement|calls">`,
`<uml-sequence name="…" root="…">`. Tag parsing is intentionally forgiving — a malformed tag
is skipped, never fatal.

Render them with `--name`:

```bash
cdec render demo.xmi --diagram activity --name checkout -o checkout.svg
```

---

## Part 12 — Troubleshooting

**`cdec: command not found`**
The console script is not on `PATH`. Use `python -m code_constraints.cli …`, or activate the
venv (`.venv/Scripts/activate` on Windows, `.venv/bin/activate` elsewhere).

**`GraphvizNotFound` / render fails**
Install [Graphviz](https://graphviz.org/download/) and put `dot` on `PATH`, or set
`$CDEC_DOT_BIN` to the binary. Only `cdec render` and sequence diagrams in the viewer need
it — parsing, diffing, and all four engines do not.

**Web UI shows raw JSON instead of the app**
`frontend/dist/` is not built. Run `make frontend-build` (or `cd frontend && npm run build`).
An installed **wheel does not ship the frontend** — use a clone or the standalone installer
if you want the viewer.

**My latest frontend change isn't showing**
`cdec serve` serves the *built* bundle. Re-run `npm run build`, or use `npm run dev` for
HMR. If it still persists, restart `cdec serve` so the new `index.html` is served.

**`WinError 10013` on startup**
Port 8000 is reserved by Windows `http.sys`. The default is already 8765; if that is also
taken, use `--port`.

**`scope: diff` rules are being skipped**
No baseline is resolvable. Pass `--base-ref origin/main`, or ensure `.cdec/reference.xmi`
exists (`cdec check --automatic-exceptions reference`). Skipped rules are listed in the
report — they do not fail silently.

**A rule reports as `[skipped]` and I expected it to run**
The reason is on the same line. The usual causes are a `scope: diff` rule with no baseline,
a `tag-conformance` or `implementation-locks` rule on TypeScript or Svelte, and a
`reference-architecture` rule with no `reference.xmi` yet. A skipped rule never fails the
build, which is why it is printed — silence would be indistinguishable from a pass.

**`cdec check` says `not-baselined`**
Something is tagged `@locked` but was never recorded. Run `cdec check --automatic-exceptions locks`.

**`cdec check` says `algo-mismatch`**
The ledger was written by a different fingerprinter version. Re-baseline with
`cdec check --automatic-exceptions locks --force` after reviewing.

**A lock trips on a change I think is cosmetic**
Locks ignore formatting, comments, moves, and (by default) docstrings — but they do *not*
ignore renamed parameters, reordered arguments, or changed literals. If `include_docstrings:
true` is set in `rules.yaml`, docstring edits count too.

**the `tag-conformance` rule false positives in Python**
Detection is heuristic. Add the offending name to `allow=[…]` on the tag.

**`cdec check` says nothing about my `@locked` code**
Locks are opt-in like every other rule. Add an `implementation-locks` entry to
`rules.yaml`; without one, `cdec check` does not look at the tags.

**`missing {config_dir}/rules.yaml`**
The project has not been scaffolded. Run `cdec init --lang <lang> --source <dir>`. If it
predates the single-file layout and still has `config.yaml`, run `cdec init --migrate`.

**A rule tag isn't being recognised**
It must be imported from the shim namespace — `from cdec_rules import …` or
`using CodeConstraints.Rules;`. A locally-defined decorator with the same name is ignored by
design. Run `cdec update-assets` if the shim is missing or stale.

---

## Where to go next

- **[Rules & constraints catalogue](RULES_CATALOGUE.md)** — every rule and tag, with options,
  a sample configuration, and passing/failing examples. The reference to keep open while you
  write `rules.yaml`.
- **[CLI reference](CLI_REFERENCE.md)** — every command, option, and config file.
- **[Examples](../examples/README.md)** — the demo projects used throughout this tutorial.
- **[Project README](../README.md)** — overview, install, and build instructions.

The bundled demos are the best next step: `examples/python_demo` and
`examples/csharp_demo` each carry a fully-commented `rules.yaml` — settings, twelve model
rules, a `tag-conformance` rule, an `implementation-locks` rule and a committed lock
digest — plus tagged classes and one intentional seeded violation, so you can watch a real
failure and fix it.

```bash
make demo      # runs `cdec check` against every demo
```
